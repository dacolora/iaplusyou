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

# (tipo, cada_segundos). Los tipos se registran en tareas/. El orden importa
# dentro de un mismo tick: los pedidos de las tiendas se sincronizan (y se
# atribuyen) ANTES de refrescar experimentos, así el snapshot por tienda ve
# las ventas de este ciclo y no las de hace 2 h.
PERIODICAS = [("tienda_sync_pedidos_todas", 7200), ("exp_refrescar_todos", 7200), ("exp_decidir_todos", 3600),
              ("exp_avanzar_todos", 600), ("tienda_sync_productos_todas", 21600)]

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


MENSAJE_INTERRUMPIDA = "Se interrumpió por un reinicio del servidor. Vuelve a intentar."


def recuperar_interrumpidas(minutos):
    """cola.recuperar_colgadas + hooks: la tarea que quedó en `error` sin más
    reintentos deja atrás una sesión en `video_generando`, un swap en
    `generando` o un anuncio en `publicando` que nadie más va a tocar. Cada
    tipo registra en tareas.AL_INTERRUMPIR cómo marcar esa entidad en error
    para que la persona pueda reintentar. Un hook que falla no tumba el ciclo.
    Devuelve cuántas tareas tocó recuperar_colgadas (mismo número de antes)."""
    tocadas, interrumpidas = cola.recuperar_colgadas(minutos)
    for t in interrumpidas:
        hook = tareas.AL_INTERRUMPIR.get(t["tipo"])
        if hook is None:
            continue
        try:
            hook(t, MENSAJE_INTERRUMPIDA)
            log.info("tarea %s interrumpida → entidad marcada en error", t["id"])
        except Exception as e:  # noqa: BLE001 — el hook nunca tumba al worker
            log.error("tarea %s interrumpida: el hook de %s falló: %s", t["id"], t["tipo"], cola.sin_token(e))
    return tocadas


def ciclo():
    if debe_parar():
        return False
    recuperar_interrumpidas(30)
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
    huerfanas = recuperar_interrumpidas(0)
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
