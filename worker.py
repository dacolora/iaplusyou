"""
Worker de Creatv Machine: proceso aparte de gunicorn (servicio systemd
creatv-worker) que ejecuta las tareas de la cola persistente (cola.py) una a la
vez. Si el proceso muere a mitad de una tarea, esa tarea vuelve a `pendiente`
a los 30 min (recuperar_colgadas) y se reintenta — a diferencia de los hilos
en memoria de trabajos.py, nada se pierde con un reinicio.

Uso: `python worker.py` (carga .env como dashboard.py).
"""
import logging
import os
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


def encolar_periodicas():
    """Encola cada periódica cuando pasó su ventana desde la última vez (kv)."""
    ahora = datetime.now()
    with db.conectar() as con:
        for tipo, cada in PERIODICAS:
            clave = f"ultimo_{tipo}"
            ultimo = con.execute(sa.select(db.kv.c.valor).where(db.kv.c.clave == clave)).scalar()
            if ultimo and datetime.fromisoformat(ultimo) + timedelta(seconds=cada) > ahora:
                continue
            con.execute(insert_sqlite(db.kv).values(
                clave=clave, valor=ahora.isoformat(timespec="seconds"), actualizado_en=db.ahora()
            ).on_conflict_do_update(index_elements=["clave"], set_={"valor": ahora.isoformat(timespec="seconds"), "actualizado_en": db.ahora()}))
    for tipo, _ in PERIODICAS:
        if _recien_marcada(tipo, ahora):
            cola.encolar(tipo, {}, job_id=f"periodica__{tipo}")


def _recien_marcada(tipo, ahora):
    with db.conectar() as con:
        valor = con.execute(sa.select(db.kv.c.valor).where(db.kv.c.clave == f"ultimo_{tipo}")).scalar()
    return valor == ahora.isoformat(timespec="seconds")


def ejecutar(tarea):
    fn = tareas.REGISTRO.get(tarea["tipo"])
    if fn is None:
        raise RuntimeError(f"tipo de tarea desconocido: {tarea['tipo']}")
    return fn(tarea)


def ciclo():
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
    log.info("worker arriba · base %s · tipos %s", db.url(), sorted(tareas.REGISTRO))
    while True:
        try:
            if not ciclo():
                time.sleep(2)
        except Exception as e:  # noqa: BLE001
            log.error("ciclo falló: %s", cola.sin_token(e))
            time.sleep(5)


if __name__ == "__main__":
    main()
