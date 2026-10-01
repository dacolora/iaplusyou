"""registro_app (spec 2026-10-01-escala-y-monitoreo §6.3): el archivo de
registro por proceso, la copia de los print(), log.error → errores agrupados
sin contarlo dos veces, y el lector de /admin/salud/registros. `configurar`
cambia el logging y la salida estándar del proceso, así que corre en un
proceso aparte."""
import os
import subprocess
import sys
import textwrap

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture()
def logs(tmp_path, monkeypatch):
    monkeypatch.setenv("CREATV_LOGS", str(tmp_path))
    return tmp_path


def test_leer_agrupa_las_lineas_de_cada_entrada_y_filtra(logs):
    import registro_app
    (logs / "web.log").write_text(
        "2026-10-01 10:00:00,001 INFO creatv.salida: arrancó\n"
        "2026-10-01 10:00:01,002 WARNING creatv.salida: [aviso] Gasto de acme: algo\n"
        "2026-10-01 10:00:02,003 ERROR dashboard: Exception on /x [GET]\n"
        "Traceback (most recent call last):\n"
        "ValueError: con Bearer abcdefghijklmn\n", encoding="utf-8")
    todo = registro_app.leer("web")
    assert [e["nivel"] for e in todo] == ["ERROR", "WARNING", "INFO"]          # la más nueva primero
    assert todo[0]["texto"].startswith("Exception on /x") and "ValueError" in todo[0]["texto"]
    assert "abcdefghijklmn" not in todo[0]["texto"]
    assert [e["nivel"] for e in registro_app.leer("web", nivel="WARNING")] == ["ERROR", "WARNING"]
    assert [e["nivel"] for e in registro_app.leer("web", nivel="ERROR")] == ["ERROR"]
    assert [e["origen"] for e in registro_app.leer("web", buscar="ACME")] == ["creatv.salida"]
    assert len(registro_app.leer("web", n=1)) == 1
    with pytest.raises(ValueError):
        registro_app.ruta("../../etc/passwd")


def test_leer_sigue_con_el_archivo_rotado_y_sin_archivo_da_vacio(logs):
    import registro_app
    assert registro_app.leer("worker") == []
    (logs / "worker.log.1").write_text("2026-10-01 09:00:00,000 INFO creatv.worker: vieja\n", encoding="utf-8")
    (logs / "worker.log").write_text("2026-10-01 10:00:00,000 INFO creatv.worker: nueva\n", encoding="utf-8")
    assert [e["texto"] for e in registro_app.leer("worker")] == ["nueva", "vieja"]
    assert registro_app.tamano_total() > 0


def test_configurar_escribe_el_archivo_copia_los_print_y_registra_los_errores(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'r.db'}"
    guion = textwrap.dedent("""
        import logging, sys
        sys.path.insert(0, %r)
        import db, monitoreo, registro_app
        db.crear_todo()
        monitoreo._avisar_en_hilo = lambda fid: None
        registro_app.configurar("worker")
        registro_app.configurar("worker")          # idempotente
        print("[aviso] algo raro con access_token=EAAB777")
        print("una línea normal")
        log = logging.getLogger("creatv.prueba")
        log.info("info suelta")
        for proyecto in ("acme", "otro"):          # la misma línea: el mismo error
            log.error("no pude sincronizar %%s", proyecto)
        log.error("ya contado", extra={"sin_monitoreo": True})
        try:
            raise KeyError("x")
        except KeyError as e:
            registro_app.marcar_registrada(e)
            log.exception("contada en otro lado")
        try:
            raise ZeroDivisionError("y")
        except ZeroDivisionError:
            log.exception("se cayó el cálculo")
        for f in monitoreo.listar(None):
            sys.__stdout__.write("FILA|%%s|%%s|%%s|%%s\\n" %% (f["origen"], f["tipo"], f["ruta"], f["veces"]))
    """) % RAIZ
    entorno = {**os.environ, "CREATV_LOGS": str(tmp_path), "CREATV_DB_URL": db_url}
    entorno.pop("PYTEST_CURRENT_TEST", None)
    r = subprocess.run([sys.executable, "-c", guion], env=entorno, capture_output=True, text=True, timeout=60, cwd=RAIZ)
    assert r.returncode == 0, r.stderr
    # La salida estándar sigue igual (journald), y además todo queda en el archivo.
    assert "una línea normal" in r.stdout
    texto = (tmp_path / "worker.log").read_text(encoding="utf-8")
    assert "WARNING creatv.salida: [aviso] algo raro" in texto and "EAAB777" not in texto
    assert "INFO creatv.salida: una línea normal" in texto and "INFO creatv.prueba: info suelta" in texto
    assert "ERROR creatv.prueba: no pude sincronizar acme" in texto and "ZeroDivisionError" in texto
    filas = sorted(l.split("|")[1:] for l in r.stdout.splitlines() if l.startswith("FILA|"))
    # Las dos «no pude sincronizar» son UNA fila (misma plantilla); la marcada y la
    # sin_monitoreo no entran; la excepción entra por su tipo.
    assert filas == [["worker", "ZeroDivisionError", "creatv.prueba", "1"],
                     ["worker", "creatv.prueba", "no pude sincronizar %s", "2"]], filas
