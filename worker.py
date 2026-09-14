"""
Worker de Creatv Machine: proceso aparte de gunicorn (servicio systemd
creatv-worker) que ejecuta las tareas de la cola persistente (cola.py) una a la
vez. Si el proceso muere a mitad de una tarea, esa tarea vuelve a `pendiente`
a los 30 min (recuperar_colgadas) y se reintenta — a diferencia de los hilos
en memoria de trabajos.py, nada se pierde con un reinicio. Al arrancar, además,
recupera de inmediato lo que quedó en_curso (solo hay un worker: es huérfano
seguro), y ante SIGINT/SIGTERM termina la tarea en curso antes de salir.

Uso: `python worker.py` (carga .env como dashboard.py).
"""
import logging
import os
import signal
import sys
import time
import traceback
from datetime import datetime, timedelta

import sqlalchemy as sa
from dotenv import load_dotenv
from sqlalchemy.dialects.sqlite import insert as insert_sqlite

import cola
import db
import tareas

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
log = logging.getLogger("creatv.worker")

# (tipo, cada_segundos). Los tipos se registran en tareas/ (bloques siguientes
# agregan refrescar_metricas_todos, sincronizar_tiendas, decidir_experimentos).
PERIODICAS = []

# Parada limpia: SIGINT/SIGTERM (systemd manda SIGINT, TimeoutStopSec=600) solo
# levantan esta bandera; el bucle termina la tarea en curso y recién ahí sale.
_PARAR = False


def debe_parar():
    return _PARAR


def _pedir_parada(signum, _frame):
    global _PARAR
    _PARAR = True
    log.info("señal %s: termino la tarea en curso y paro", signal.Signals(signum).name)


def encolar_periodicas():
    """Encola cada periódica cuando pasó su ventana desde la última vez (kv)."""
    ahora = datetime.now()
    marcadas = set()
    with db.conectar() as con:
        for tipo, cada in PERIODICAS:
            clave = f"ultimo_{tipo}"
            ultimo = con.execute(sa.select(db.kv.c.valor).where(db.kv.c.clave == clave)).scalar()
            if ultimo and datetime.fromisoformat(ultimo) + timedelta(seconds=cada) > ahora:
                continue
            con.execute(insert_sqlite(db.kv).values(
                clave=clave, valor=ahora.isoformat(timespec="seconds"), actualizado_en=db.ahora()
            ).on_conflict_do_update(index_elements=["clave"], set_={"valor": ahora.isoformat(timespec="seconds"), "actualizado_en": db.ahora()}))
            marcadas.add(tipo)
    for tipo in marcadas:
        cola.encolar(tipo, {}, job_id=f"periodica__{tipo}")


def ejecutar(tarea):
    fn = tareas.REGISTRO.get(tarea["tipo"])
    if fn is None:
        raise RuntimeError(f"tipo de tarea desconocido: {tarea['tipo']}")
    return fn(tarea)


def ciclo():
    if debe_parar():
        return False
    cola.recuperar_colgadas(30)
    encolar_periodicas()
    tarea = cola.reclamar()
    if tarea is None:
        return False
    log.info("tarea %s %s (intento %s) job=%s", tarea["id"], tarea["tipo"], tarea["intentos"], tarea["job_id"])
    try:
        mensaje = ejecutar(tarea)
        cola.terminar(tarea["id"], mensaje)
        log.info("tarea %s hecha", tarea["id"])
    except Exception as e:  # noqa: BLE001 — el worker nunca muere por una tarea
        log.error("tarea %s falló: %s\n%s", tarea["id"], cola.sin_token(e), cola.sin_token(traceback.format_exc()))
        cola.fallar(tarea["id"], f"{type(e).__name__}: {e}")
    return True


def main():
    load_dotenv(os.path.join(BASE_DIR, ".env"))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    tareas.cargar_todas()
    signal.signal(signal.SIGINT, _pedir_parada)
    signal.signal(signal.SIGTERM, _pedir_parada)
    log.info("worker arriba · base %s · tipos %s", db.url(), sorted(tareas.REGISTRO))
    # Un solo worker: lo que esté en_curso al arrancar quedó huérfano del
    # proceso anterior (murió a mitad), no hay que esperar los 30 min.
    huerfanas = cola.recuperar_colgadas(0)
    if huerfanas:
        log.info("recuperadas %s tareas que quedaron en curso del proceso anterior", huerfanas)
    while not debe_parar():
        try:
            if not ciclo() and not debe_parar():
                time.sleep(2)
        except KeyboardInterrupt:
            _pedir_parada(signal.SIGINT, None)
        except Exception as e:  # noqa: BLE001
            log.error("ciclo falló: %s", cola.sin_token(e))
            time.sleep(5)
    log.info("worker parado")


if __name__ == "__main__":
    main()
