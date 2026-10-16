"""PND-269 (decisión 2026-10-13): las pruebas escriben en carpetas temporales y una guarda falla si el árbol
de trabajo cambia. La guarda vive en `tests/conftest.py` (`foto_arbol`, `pytest_configure`,
`pytest_sessionfinish`); aquí se prueba sobre un repositorio de git de mentira, no sobre el checkout."""
import os
import subprocess
from types import SimpleNamespace

import pytest

from tests import conftest


def _git(raiz, *args):
    subprocess.run(["git", *args], cwd=raiz, check=True, capture_output=True, text=True)


@pytest.fixture()
def repo(tmp_path):
    raiz = tmp_path / "repo"
    raiz.mkdir()
    _git(raiz, "init", "-q")
    (raiz / ".gitignore").write_text("registro_generaciones.csv\nclientes/*/referencias_pendientes.json\n")
    (raiz / "app.py").write_text("x = 1\n")
    _git(raiz, "add", ".")
    _git(raiz, "-c", "user.email=prueba@prueba.local", "-c", "user.name=prueba", "commit", "-q", "-m", "inicio")
    return raiz


def test_la_foto_ve_lo_ignorado_lo_nuevo_y_lo_cambiado_archivo_por_archivo(repo):
    antes = conftest.foto_arbol(str(repo))
    assert antes == set()
    (repo / "registro_generaciones.csv").write_text("fecha\n")                 # ignorado, en la raíz
    (repo / "clientes" / "acme").mkdir(parents=True)
    (repo / "clientes" / "acme" / "referencias_pendientes.json").write_text("[]")  # ignorado, en una carpeta nueva
    (repo / "suelto.txt").write_text("hola")                                   # sin seguir
    (repo / "app.py").write_text("x = 2\n")                                    # versionado que cambió
    (repo / "__pycache__").mkdir()
    (repo / "__pycache__" / "app.cpython-39.pyc").write_bytes(b"\0")          # no cuenta
    nuevos = conftest.arbol_nuevo(antes, conftest.foto_arbol(str(repo)))
    assert nuevos == sorted(["!! registro_generaciones.csv", "!! clientes/acme/referencias_pendientes.json",
                             "?? suelto.txt", " M app.py"])


def test_lo_que_ya_estaba_antes_no_cuenta(repo):
    (repo / "registro_generaciones.csv").write_text("fecha\n")
    antes = conftest.foto_arbol(str(repo))
    (repo / "registro_generaciones.csv").write_text("fecha\notra fila\n")
    assert conftest.arbol_nuevo(antes, conftest.foto_arbol(str(repo))) == []


def test_fuera_de_git_no_hay_guarda(tmp_path):
    assert conftest.foto_arbol(str(tmp_path)) is None


class _Reporter:
    def __init__(self):
        self.lineas = []

    def write_line(self, linea, **_kw):
        self.lineas.append(linea)


def _sesion(raiz, foto):
    reporter = _Reporter()
    config = SimpleNamespace(_creatv_arbol=(str(raiz), foto),
                             pluginmanager=SimpleNamespace(get_plugin=lambda nombre: reporter))
    return SimpleNamespace(config=config, exitstatus=pytest.ExitCode.OK), reporter


def test_la_corrida_falla_y_dice_que_quedo_si_el_arbol_cambio(repo):
    sesion, reporter = _sesion(repo, conftest.foto_arbol(str(repo)))
    (repo / "registro_generaciones.csv").write_text("fecha\n")
    conftest.pytest_sessionfinish(sesion, 0)
    assert sesion.exitstatus == pytest.ExitCode.TESTS_FAILED
    assert any("PND-269" in linea for linea in reporter.lineas)
    assert "  !! registro_generaciones.csv" in reporter.lineas


def test_la_corrida_sigue_igual_si_el_arbol_no_cambio(repo):
    sesion, reporter = _sesion(repo, conftest.foto_arbol(str(repo)))
    conftest.pytest_sessionfinish(sesion, 0)
    assert sesion.exitstatus == pytest.ExitCode.OK and reporter.lineas == []


def test_la_guarda_se_apaga_con_la_variable(monkeypatch):
    monkeypatch.setenv("CREATV_SIN_GUARDA_ARBOL", "1")
    config = SimpleNamespace()
    conftest.pytest_configure(config)
    assert not hasattr(config, "_creatv_arbol")


def test_la_bitacora_y_la_bandeja_de_crear_van_a_la_carpeta_temporal(tmp_path):
    """Los dos archivos que la suite dejaba en el checkout (revisión final de E2, 2026-10-10)."""
    import bitacora
    import referencias_flowplus
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bitacora.registrar("acme", "b1", "prueba", "ok")
    referencias_flowplus.agregar("acme", "imagen", "https://r2/a.jpg")
    assert os.path.dirname(bitacora.LOG_FILE) == str(tmp_path) and os.path.exists(bitacora.LOG_FILE)
    assert referencias_flowplus._path("acme").startswith(str(tmp_path) + os.sep)
    assert os.path.exists(referencias_flowplus._path("acme"))
    assert not bitacora.LOG_FILE.startswith(raiz + os.sep)


def test_la_cola_de_aprobacion_va_a_la_carpeta_temporal(tmp_path):
    """Un video de Crear que termina por el worker toca `estado.modificar`, que abre `estado_videos.json.lock`
    (lo dejaban test_i18n_guardado, test_lanzamiento_incierto, test_lote6_costos y test_seedance_referencias_fal)."""
    import estado
    estado.modificar("acme", lambda e: {**e, "cf_1": {"estado": "pendiente"}})
    assert estado._path("acme").startswith(str(tmp_path) + os.sep)
    assert os.path.exists(estado._path("acme") + ".lock")


def test_sin_base_temporal_la_base_tampoco_es_la_del_checkout():
    """Sin `CREATV_DB_URL`, db.url() es data/creatv.db del checkout (la base real en el principal); una prueba que
    toca la base sin `base_temporal` la creaba (test_lote3_seguridad::test_el_plazo_corre_desde_que_se_tiene_el_candado)."""
    import db
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert os.path.join(raiz, "data", "creatv.db") not in db.url()
    assert db.url().startswith("sqlite:///") and conftest._BASE_SESION in db.url()
