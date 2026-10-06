"""deploy/cola_vacia.py dice «no reiniciar» mientras haya algo vivo en la cola."""
import os
import sqlite3
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(RAIZ, "deploy", "cola_vacia.py")


def base(tmp_path, filas):
    ruta = tmp_path / "creatv.db"
    con = sqlite3.connect(ruta)
    con.execute("CREATE TABLE tarea (id INTEGER PRIMARY KEY, tipo TEXT, cliente TEXT, estado TEXT, "
                "ejecutar_desde TEXT)")
    con.executemany("INSERT INTO tarea (tipo, cliente, estado, ejecutar_desde) VALUES (?, ?, ?, ?)", filas)
    con.commit()
    con.close()
    return ruta


def correr(ruta):
    entorno = dict(os.environ, CREATV_DB_URL="sqlite:///%s" % ruta)
    return subprocess.run([sys.executable, SCRIPT], capture_output=True, text=True, env=entorno, timeout=30)


def test_cola_vacia_deja_reiniciar(tmp_path):
    r = correr(base(tmp_path, [("flowplus_video", "happyflops", "hecha", "2026-10-01T08:00:00"),
                               ("exp_refrescar_todos", None, "pendiente", "2999-01-01T00:00:00")]))
    assert r.returncode == 0, r.stdout
    assert "cola vacía" in r.stdout


def test_una_tarea_en_curso_frena(tmp_path):
    r = correr(base(tmp_path, [("flowplus_imagen", "happyflops", "en_curso", "2026-10-01T08:00:00")]))
    assert r.returncode == 1
    assert "flowplus_imagen" in r.stdout and "NO reiniciar" in r.stdout


def test_una_pendiente_cuya_hora_llego_frena(tmp_path):
    r = correr(base(tmp_path, [("final_producir", "colorado_forja", "pendiente", "2000-01-01T00:00:00")]))
    assert r.returncode == 1
    assert "final_producir" in r.stdout
