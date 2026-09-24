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


# Usuarios que los tests de rutas meten en la sesión a mano (session_transaction).
# El guard _verificar_sesion cierra cualquier sesión cuyo usuario no esté en
# usuarios.json, así que tienen que existir. Contraseña de todos: PASSWORD_PRUEBA.
PASSWORD_PRUEBA = "prueba-1234"
USUARIOS_PRUEBA = {
    "admin": {"rol": "admin", "cliente": None, "correo": "admin@prueba.local", "correo_verificado": True},
    "alguien": {"rol": "cliente", "cliente": "acme", "correo": "alguien@prueba.local", "correo_verificado": True},
    "user_acme": {"rol": "cliente", "cliente": "acme", "correo": "acme@prueba.local", "correo_verificado": True},
    "otro": {"rol": "cliente", "cliente": "otro", "correo": "otro@prueba.local", "correo_verificado": True},
}
_hash_prueba = []


def sembrar_usuarios(ruta, nombres=None):
    """Escribe en `ruta` los USUARIOS_PRUEBA (o solo `nombres`) con un hash
    real de PASSWORD_PRUEBA calculado una sola vez por sesión de pytest (pbkdf2
    es lento a propósito; hacerlo por test costaría minutos)."""
    import _json_store
    if not _hash_prueba:
        import usuarios
        _hash_prueba.append(usuarios._hash(PASSWORD_PRUEBA))
    data = {}
    for nombre, campos in USUARIOS_PRUEBA.items():
        if nombres is not None and nombre not in nombres:
            continue
        data[nombre] = {"password_hash": _hash_prueba[0], "session_version": 1,
                        "creado_en": "2026-01-01T00:00:00", **campos}
    _json_store.guardar(str(ruta), data)
    return data


@pytest.fixture(autouse=True)
def usuarios_tmp(tmp_path, monkeypatch, request):
    """usuarios.json temporal por test, con USUARIOS_PRUEBA sembrados: ningún
    test lee ni escribe el usuarios.json real del repo, y las sesiones falsas
    de los tests de rutas (admin, alguien, user_acme, otro) pasan el guard.
    Devuelve el módulo `usuarios`; un test que quiera el archivo vacío lo
    repunta con monkeypatch (tests/test_cuentas.py, test_rutas_cuentas.py).
    Se salta para tests que necesitan tmp_path vacío (referentes.imagenes)."""
    # Skip for referentes imagenes tests (need clean tmp_path)
    if 'test_referentes_imagenes' in request.node.nodeid:
        return None
    import usuarios
    ruta = tmp_path / "usuarios_prueba.json"
    monkeypatch.setattr(usuarios, "_path", lambda: str(ruta))
    sembrar_usuarios(ruta)
    return usuarios


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
