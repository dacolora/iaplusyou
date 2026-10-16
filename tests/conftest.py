import os
import shutil
import subprocess
import sys
import tempfile

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

# PND-269: sin `CREATV_DB_URL`, db.url() es data/creatv.db del checkout, la base REAL en el checkout principal.
# Una prueba que toca la base sin pedir `base_temporal` la creaba (o escribía en ella). Toda la sesión apunta a
# una base temporal; `base_temporal` sigue dando una nueva por prueba encima de esta.
_BASE_SESION = tempfile.mkdtemp(prefix="creatv_sesion_")
os.environ["CREATV_DB_URL"] = f"sqlite:///{os.path.join(_BASE_SESION, 'creatv.db')}"


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
    # El motor ya se soltó: la carpeta (con sus -wal/-shm) se borra. Sin esto
    # cada test dejaba una carpeta en $TMPDIR (31 000 y 25 GB, 2026-10-10).
    shutil.rmtree(carpeta, ignore_errors=True)


@pytest.fixture()
def margen_1_5(base_temporal):
    """El margen global que suponen los tests de cobros que no hablan del margen. El defecto del código es 2,0
    (a la carta, planes 2026-10-09); estos tests escriben su lógica con 1,5 y lo fijan aquí, explícito."""
    from cobros import libro
    libro.guardar_margen_global(1.5, "test")
    yield


@pytest.fixture()
def escritor_en_medio(base_temporal):
    """`escritor_en_medio(patron, sql)`: justo antes del primer statement que
    contenga `patron`, OTRA conexión (otro hilo, el worker) ejecuta `sql` y
    confirma. Si la transacción en curso ya tiene el candado de escritura, esa
    conexión queda bloqueada (timeout corto) y no escribe nada: devuelve el
    estado {"hecho", "resultado": "confirmó" | "bloqueado: …"}."""
    import sqlite3

    import sqlalchemy as sa

    ruta = str(base_temporal.engine().url.database)

    def armar(patron, sql):
        estado = {"hecho": False, "resultado": None}

        @sa.event.listens_for(base_temporal.engine(), "before_cursor_execute")
        def _antes(conn, cursor, statement, params, context, executemany):
            if estado["hecho"] or patron not in statement:
                return
            estado["hecho"] = True
            otro = sqlite3.connect(ruta, timeout=0.3)
            try:
                otro.execute(sql)
                otro.commit()
                estado["resultado"] = "confirmó"
            except sqlite3.OperationalError as e:
                estado["resultado"] = f"bloqueado: {e}"
            finally:
                otro.close()
        return estado
    return armar


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
def usuarios_tmp(tmp_path, monkeypatch):
    """usuarios.json temporal por test, con USUARIOS_PRUEBA sembrados: ningún
    test lee ni escribe el usuarios.json real del repo, y las sesiones falsas
    de los tests de rutas (admin, alguien, user_acme, otro) pasan el guard.
    Devuelve el módulo `usuarios`; un test que quiera el archivo vacío lo
    repunta con monkeypatch (tests/test_cuentas.py, test_rutas_cuentas.py)."""
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


@pytest.fixture(autouse=True)
def registros_en_tmp(tmp_path, monkeypatch):
    """PND-269 (decisión 2026-10-13): la bitácora (`registro_generaciones.csv` en la raíz), la bandeja de
    referencias de Crear (`clientes/<c>/referencias_pendientes.json`) y la cola de aprobación
    (`clientes/<c>/estado_videos.json` y su `.lock`) se escriben en la carpeta temporal del test, nunca en el árbol
    de trabajo: en el checkout principal se mezclaban con los datos reales. Un test que
    necesita otra carpeta la repunta con su propio monkeypatch (gana el último). Ojo con el nombre: pytest arma
    los autouse por orden alfabético, y uno que pida `monkeypatch` antes de `_sin_cache_meta` hace que este limpie
    con los parches del test todavía puestos (test_rutas_alertas::test_invalidar_tras_escribir… fallaba al cerrar)."""
    import bitacora
    import estado
    import referencias_flowplus
    monkeypatch.setattr(bitacora, "LOG_FILE", str(tmp_path / "registro_generaciones.csv"))
    monkeypatch.setattr(referencias_flowplus, "BASE_DIR", str(tmp_path))
    # La cola de aprobación (`clientes/<c>/estado_videos.json` y su `.lock`): un video de Crear que termina por el
    # worker la toca con `estado.modificar`, que abre el candado aunque el test haya fingido cargar/guardar.
    monkeypatch.setattr(estado, "BASE_DIR", str(tmp_path))


# ---- PND-269: guarda del árbol de trabajo ----
# Lo que una corrida de pruebas deja en el checkout (un archivo nuevo, ignorado o no, o uno versionado que cambió)
# hace fallar la corrida al final, con la lista. Fuera de la cuenta: venv, worktrees de otras conversaciones, el
# submódulo y los __pycache__. `CREATV_SIN_GUARDA_ARBOL=1` la apaga (por ejemplo, si a la vez estás editando
# archivos en el mismo checkout o la app corre ahí y escribe sus datos).
_ARBOL_FUERA = (":(exclude)venv", ":(exclude).venv", ":(exclude).claude/worktrees", ":(exclude)meta_ads",
                ":(exclude)node_modules")


def foto_arbol(raiz=RAIZ):
    """Las líneas de `git status` (cambiados, sin seguir e ignorados, archivo por archivo) del árbol de `raiz`.
    None si no es un repositorio de git o git no responde: entonces no hay guarda."""
    try:
        r = subprocess.run(["git", "status", "--porcelain", "--ignored", "--untracked-files=all", "--", ".",
                            *_ARBOL_FUERA], cwd=raiz, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return {linea for linea in r.stdout.splitlines()
            if "__pycache__" not in linea and ".pytest_cache" not in linea}


def arbol_nuevo(antes, despues):
    """Lo que apareció en el árbol entre las dos fotos (lo que ya estaba antes no cuenta)."""
    return sorted((despues or set()) - (antes or set()))


def pytest_configure(config):
    # pytest_configure y no pytest_sessionstart: con `pytest` a secas desde la raíz este conftest se carga al
    # recolectar, después de sessionstart, y la guarda quedaba apagada sin decirlo.
    if os.environ.get("CREATV_SIN_GUARDA_ARBOL") or hasattr(config, "_creatv_arbol"):
        return
    config._creatv_arbol = (RAIZ, foto_arbol(RAIZ))


def pytest_unconfigure(config):
    shutil.rmtree(_BASE_SESION, ignore_errors=True)


def pytest_sessionfinish(session, exitstatus):
    raiz, antes = getattr(session.config, "_creatv_arbol", (None, None))
    if antes is None:
        return
    nuevos = arbol_nuevo(antes, foto_arbol(raiz))
    if not nuevos:
        return
    lineas = ["", "Guarda del árbol (PND-269): las pruebas dejaron esto en el checkout; deben escribir en tmp_path:"]
    lineas += ["  " + n for n in nuevos]
    lineas.append("(Si lo cambiaste tú mientras corrían, o la app corre en este checkout: CREATV_SIN_GUARDA_ARBOL=1.)")
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    for linea in lineas:
        if reporter is not None:
            reporter.write_line(linea, red=True)
        else:
            print(linea, file=sys.stderr)
    session.exitstatus = pytest.ExitCode.TESTS_FAILED


@pytest.fixture(autouse=True)
def idioma_de_tests(monkeypatch):
    """Los tests existentes comparan textos en español: el idioma por defecto
    queda fijo en "es" aunque idiomas.DEFECTO cambie a "en" (fase 6). Un test
    de inglés lo pide explícitamente (usuario con idioma "en" o cookie)."""
    import idiomas
    monkeypatch.setattr(idiomas, "DEFECTO", "es")
    monkeypatch.setattr(idiomas, "ACTIVO_PARA_TODOS", False)


def _jpg_valido():
    import io

    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (2, 2), (120, 80, 40)).save(buf, format="JPEG")
    return buf.getvalue()


# Una foto JPEG de verdad (2×2) para los tests que suben fotos por una ruta:
# desde la auditoría de seguridad 2026-10-01 el servidor mira el contenido,
# y unos bytes que solo empiezan como JPEG ya no pasan.
JPG_VALIDO = _jpg_valido()
