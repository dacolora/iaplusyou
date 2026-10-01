"""
Worker de Creatv Machine: proceso aparte de gunicorn (servicio systemd
creatv-worker) que ejecuta las tareas de la cola persistente (cola.py) en dos
carriles (spec 2026-09-28-crear-sin-cola):

- **crear**: las generaciones de Crear (`CARRIL_CREAR`) en hasta `HILOS_CREAR`
  hilos a la vez — casi todo su tiempo es esperar al proveedor, y una espera
  colgada (Wan 3.0 llegó a 20 min) ya no deja a las demás en fila. Los lotes de
  Sprints (prioridad < 5) ocupan como mucho `HILOS_LOTE`, así una pieza suelta
  siempre encuentra hilo.
- **general**: todo lo demás, de a una y en orden, como siempre (renders con
  1 CPU, Meta, periódicas…).

El hilo principal solo supervisa (`repartir`). Si el proceso muere a mitad de
una tarea, esa tarea vuelve a `pendiente` a los 30 min (recuperar_colgadas) y
se reintenta — nunca una que este mismo proceso está ejecutando. Al arrancar
recupera de inmediato lo que quedó en_curso (solo hay un worker: es huérfano
seguro), y ante SIGINT/SIGTERM deja de repartir, corta las esperas a WaveSpeed
(pasan la posta a `flowplus_recuperar`) y espera a que terminen los hilos.

Uso: `python worker.py` (carga .env como dashboard.py).
"""
import logging
import os
import signal
import sys
import threading
import time
import traceback
from datetime import datetime, timedelta

import sqlalchemy as sa
from dotenv import load_dotenv
from PIL import Image
from flask_babel import gettext
from sqlalchemy.dialects.sqlite import insert as insert_sqlite

import cola
import db
import idiomas
import tareas
from providers import wavespeed_common

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Como en dashboard.py: Pillow rechaza una imagen-bomba (pocos KB que se
# descomprimen a cientos de MB) desde el doble de esto, no desde ~180 MP.
Image.MAX_IMAGE_PIXELS = 64_000_000
log = logging.getLogger("creatv.worker")

# (tipo, cada_segundos). Los tipos se registran en tareas/. El orden importa
# dentro de un mismo tick: los pedidos de las tiendas se sincronizan (y se
# atribuyen) ANTES de refrescar experimentos, así el snapshot por tienda ve
# las ventas de este ciclo y no las de hace 2 h; lo mismo Triple Whale.
PERIODICAS = [("tienda_sync_pedidos_todas", 7200), ("tw_sincronizar_todas", 7200), ("exp_refrescar_todos", 7200),
              ("exp_decidir_todos", 3600),
              ("exp_avanzar_todos", 600), ("tienda_sync_productos_todas", 21600), ("sprint_qa_pendientes", 300),
              ("materiales_limpiar", 86400),
              # Auditoría 2026-09-28: salidas/ crecía 2 GB cada dos semanas, tarea
              # sumaba ~485 filas vacías al día y la base solo se respaldaba a mano.
              ("salidas_limpiar", 86400), ("cola_limpiar", 86400), ("db_respaldar", 86400),
              # Cadena de escenas de Flow Plus (spec 2026-09-30): avanza cada cadena viva
              # cuando su escena en curso termina (gratis; las escenas las cobra Crear).
              ("cadena_vigilar", 60)]

# Carril de Crear: generaciones que casi todo el tiempo esperan al proveedor
# (también la voz del anuncio hablado, que no debe esperar detrás de un render).
CARRIL_CREAR = ("flowplus_video", "flowplus_imagen", "flowplus_recuperar", "flowplus_director", "hablado_voz")
HILOS_CREAR = 4
HILOS_LOTE = 2
PRIORIDAD_SUELTA = 5    # flowplus_lanzar.PRIORIDAD_NORMAL: una pieza pedida desde Crear

# Parada limpia: SIGINT/SIGTERM (systemd manda SIGINT, TimeoutStopSec=600) solo
# levantan esta bandera; el supervisor deja de repartir y espera a sus hilos.
_PARAR = False

# Tareas que este proceso está ejecutando: {id: {"hilo", "carril", "prioridad"}}.
_EN_VUELO = {}
_LOCK_VUELO = threading.Lock()


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


def idioma_de_tarea(tarea):
    """Alias de idiomas.de_tarea (los tests y el resto del worker lo llaman así)."""
    return idiomas.de_tarea(tarea)


def ejecutar(tarea):
    """Corre la tarea en el idioma de su proyecto (spec 2026-09-26 §B8): todo
    gettext de adentro — motivos, eventos, avisos, el mensaje que devuelve y
    el texto de una excepción — sale en ese idioma."""
    with idiomas.en_idioma(idiomas.de_tarea(tarea)):
        fn = tareas.REGISTRO.get(tarea["tipo"])
        if fn is None:
            raise RuntimeError(gettext("tipo de tarea desconocido: %(tipo)s", tipo=tarea["tipo"]))
        return fn(tarea)


# Se guarda en la entidad de atrás (sesión, swap, anuncio): va en el idioma
# del proyecto de cada tarea — gettext dentro de idiomas.en_idioma(de_tarea).
MENSAJE_INTERRUMPIDA = idiomas.N_("Se interrumpió por un reinicio del servidor. Vuelve a intentar.")


def en_vuelo():
    """Ids de las tareas que este worker está ejecutando ahora."""
    with _LOCK_VUELO:
        return set(_EN_VUELO)


def recuperar_interrumpidas(minutos):
    """cola.recuperar_colgadas + hooks: la tarea que quedó en `error` sin más
    reintentos deja atrás una sesión en `video_generando`, un swap en
    `generando` o un anuncio en `publicando` que nadie más va a tocar. Cada
    tipo registra en tareas.AL_INTERRUMPIR cómo marcar esa entidad en error
    para que la persona pueda reintentar. Un hook que falla no tumba el ciclo.
    Devuelve cuántas tareas tocó recuperar_colgadas (mismo número de antes)."""
    tocadas, interrumpidas = cola.recuperar_colgadas(minutos, excluir=en_vuelo())
    for t in interrumpidas:
        hook = tareas.AL_INTERRUMPIR.get(t["tipo"])
        if hook is None:
            continue
        try:
            with idiomas.en_idioma(idiomas.de_tarea(t)):
                hook(t, gettext(MENSAJE_INTERRUMPIDA))
            log.info("tarea %s interrumpida → entidad marcada en error", t["id"])
        except Exception as e:  # noqa: BLE001 — el hook nunca tumba al worker
            log.error("tarea %s interrumpida: el hook de %s falló: %s", t["id"], t["tipo"], cola.sin_token(e))
    return tocadas


def _correr(tarea):
    """Ejecuta una tarea ya reclamada y deja su fila cerrada: hecha, hecha y
    seguida por otra (`tareas.Continuar`), o fallada (con reintento si le
    quedan). Nunca lanza: el worker no muere por una tarea."""
    log.info("tarea %s %s (intento %s) job=%s", tarea["id"], tarea["tipo"], tarea["intentos"], tarea["job_id"])
    try:
        resultado = ejecutar(tarea)
        if isinstance(resultado, tareas.Continuar):
            nueva = _terminar_y_encolar(tarea, resultado)
            log.info("tarea %s hecha; sigue en la tarea %s (%s)", tarea["id"], nueva, resultado.tipo)
        else:
            cola.terminar(tarea["id"], resultado)
            log.info("tarea %s hecha", tarea["id"])
    except ContinuacionPerdida as e:
        log.error("tarea %s: no se pudo encolar su continuación: %s", tarea["id"], cola.sin_token(e))
    except Exception as e:  # noqa: BLE001 — el worker nunca muere por una tarea
        log.error("tarea %s falló: %s\n%s", tarea["id"], cola.sin_token(e), cola.sin_token(traceback.format_exc()))
        cola.fallar(tarea["id"], f"{type(e).__name__}: {e}")


class ContinuacionPerdida(RuntimeError):
    """No se pudo cerrar la tarea y encolar su continuación (la base seguía
    ocupada tras varios intentos)."""


def _terminar_y_encolar(tarea, siguiente):
    """cola.terminar_y_encolar con reintentos: con varios hilos y gunicorn
    escribiendo, «database is locked» puede pasar. Si igual falla, la tarea
    queda en error y corre su gancho de interrupción — la entidad de atrás
    (p. ej. una sesión que quedó «generando» esperando la continuación) no
    queda colgada: el gancho la retoma o la deja con su botón."""
    ultimo = None
    for intento in range(4):
        try:
            return cola.terminar_y_encolar(tarea["id"], siguiente.mensaje, {
                "tipo": siguiente.tipo, "payload": siguiente.payload, "ejecutar_desde": siguiente.ejecutar_desde})
        except Exception as e:  # noqa: BLE001
            ultimo = e
            time.sleep(1 + intento)
    # Este hilo ya salió de ejecutar (y de su idioma): lo que se guarda va en el del proyecto.
    with idiomas.en_idioma(idiomas.de_tarea(tarea)):
        cola.fallar(tarea["id"], gettext("No se pudo encolar la continuación (%(error)s)",
                                         error=f"{type(ultimo).__name__}: {ultimo}"))
    hook = tareas.AL_INTERRUMPIR.get(tarea["tipo"])
    if hook is not None:
        try:
            with idiomas.en_idioma(idiomas.de_tarea(tarea)):
                hook(tarea, gettext(MENSAJE_INTERRUMPIDA))
        except Exception as e:  # noqa: BLE001 — el gancho nunca tumba al worker
            log.error("tarea %s: el gancho de %s falló: %s", tarea["id"], tarea["tipo"], cola.sin_token(e))
    raise ContinuacionPerdida(str(ultimo))


def ciclo():
    """Un paso síncrono: reclama UNA tarea (de cualquier carril) y la ejecuta en
    este hilo. Lo usan los tests y los scripts; el servicio usa `repartir`."""
    if debe_parar():
        return False
    recuperar_interrumpidas(30)
    encolar_periodicas()
    tarea = cola.reclamar()
    if tarea is None:
        return False
    _correr(tarea)
    return True


def _en_hilo(tarea):
    try:
        _correr(tarea)
    finally:
        with _LOCK_VUELO:
            _EN_VUELO.pop(tarea["id"], None)


def _lanzar(tarea, carril):
    """Arranca la tarea en su hilo. Devuelve False si el hilo no arrancó (poca
    memoria): la tarea vuelve a pendiente sin gastar un intento, nunca queda
    tomada por nadie."""
    hilo = threading.Thread(target=_en_hilo, args=(tarea,), name=f"tarea-{tarea['id']}")
    with _LOCK_VUELO:
        _EN_VUELO[tarea["id"]] = {"hilo": hilo, "carril": carril, "prioridad": tarea.get("prioridad") or 0}
    try:
        hilo.start()
    except Exception as e:  # noqa: BLE001
        with _LOCK_VUELO:
            _EN_VUELO.pop(tarea["id"], None)
        cola.devolver(tarea["id"])
        log.error("tarea %s: no arrancó su hilo (%s); vuelve a pendiente", tarea["id"], e)
        return False
    return True


def _ocupados():
    with _LOCK_VUELO:
        vuelo = list(_EN_VUELO.values())
    crear = [v for v in vuelo if v["carril"] == "crear"]
    lotes = [v for v in crear if v["prioridad"] < PRIORIDAD_SUELTA]
    general = [v for v in vuelo if v["carril"] == "general"]
    return len(crear), len(lotes), len(general)


def repartir():
    """Un paso del supervisor: recupera colgadas, encola periódicas y llena los
    hilos libres de cada carril. Devuelve cuántas tareas arrancó."""
    if debe_parar():
        return 0
    recuperar_interrumpidas(30)
    encolar_periodicas()
    arrancadas = 0
    while not debe_parar():
        crear, lotes, _ = _ocupados()
        if crear >= HILOS_CREAR:
            break
        tarea = cola.reclamar(tipos=CARRIL_CREAR, prioridad_min=PRIORIDAD_SUELTA if lotes >= HILOS_LOTE else None)
        if tarea is None:
            break
        if not _lanzar(tarea, "crear"):
            break
        arrancadas += 1
    if not debe_parar() and _ocupados()[2] == 0:
        tarea = cola.reclamar(excluir_tipos=CARRIL_CREAR)
        if tarea is not None and _lanzar(tarea, "general"):
            arrancadas += 1
    return arrancadas


def esperar_hilos(timeout=None):
    """Espera a que terminen las tareas en vuelo (parada limpia y tests)."""
    fin = None if timeout is None else time.time() + timeout
    while True:
        with _LOCK_VUELO:
            hilos = [v["hilo"] for v in _EN_VUELO.values()]
        if not hilos:
            return True
        for h in hilos:
            h.join(None if fin is None else max(0.0, fin - time.time()))
        if fin is not None and time.time() >= fin:
            return not en_vuelo()


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
    # Una espera a WaveSpeed se corta apenas llega la parada y pasa la posta a
    # flowplus_recuperar (nada se pierde; systemd no tiene que matar a nadie).
    wavespeed_common.fijar_detener(debe_parar)
    while not debe_parar():
        try:
            if not repartir() and not debe_parar():
                time.sleep(1)
        except KeyboardInterrupt:
            _pedir_parada(signal.SIGINT, None)
        except Exception as e:  # noqa: BLE001
            log.error("repartir falló: %s", cola.sin_token(e))
            time.sleep(5)
    if en_vuelo():
        log.info("esperando que terminen %s tareas en curso", len(en_vuelo()))
    esperar_hilos()
    log.info("worker parado")


if __name__ == "__main__":
    main()
