"""Tareas periódicas de mantenimiento (auditoría de rendimiento y
almacenamiento del 2026-09-28: nada se limpiaba nunca).

  salidas_limpiar {}   diaria — borra de `salidas/` los archivos con más de
                       SALIDAS_DIAS días. Todo lo que vive ahí es una copia
                       de trabajo: el video ya está en R2 y quien lo necesita
                       de nuevo lo vuelve a bajar (final_edition._clon_local,
                       materiales.descargar, sprints.qa.archivo_local,
                       publicador.archivo_local).
  cola_limpiar {}      diaria — cola.limpiar_terminadas: filas hecha/error
                       viejas y las periódicas vacías; también las reservas
                       de saldo cuyo trabajo ya no está vivo
                       (cobros.libro.limpiar_reservas_muertas: ya no cuentan,
                       solo ocupan filas), los eventos de Bold con firma
                       inválida de más de 30 días
                       (cobros.recargas.limpiar_eventos_sin_firma) y los
                       límites de kv de más de siete días (o ilegibles).
  db_respaldar {}      diaria — copia de data/creatv.db en data/respaldos/
                       (Connection.backup, seguro con WAL), conserva las
                       últimas RESPALDOS_CONSERVAR. Antes solo había
                       respaldos a mano en cada despliegue.
  errores_limpiar {}   diaria — monitoreo.limpiar: los errores resueltos o
                       silenciados de hace más de 90 días y lo que pase de
                       2 000 filas (spec 2026-10-01-escala-y-monitoreo §6).
Ninguna gasta ni toca R2.
"""
import json
import logging
import math
import os
import sqlite3
import time
from datetime import datetime

from flask_babel import gettext
import sqlalchemy as sa

import cola
import db
import monitoreo
from tareas import registrar

log = logging.getLogger(__name__)

SALIDAS_DIAS = 14
RESPALDOS_CONSERVAR = 7
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def carpeta_salidas():
    return os.environ.get("CREATV_SALIDAS") or os.path.join(BASE_DIR, "salidas")


def limpiar_salidas(dias=SALIDAS_DIAS, raiz=None):
    """Borra los archivos de `salidas/` con más de `dias` días (por fecha de
    modificación) y las carpetas que queden vacías debajo de `salidas/<c>/`
    (nunca `salidas/` ni `salidas/<c>/`: hay escritores que las dan por
    hechas). Devuelve (archivos, bytes)."""
    raiz = raiz or carpeta_salidas()
    if not os.path.isdir(raiz):
        return 0, 0
    limite = time.time() - dias * 86400
    n = 0
    total = 0
    for carpeta, _dirs, archivos in os.walk(raiz):
        for nombre in archivos:
            ruta = os.path.join(carpeta, nombre)
            try:
                st = os.stat(ruta)
                if st.st_mtime < limite:
                    os.remove(ruta)
                    n += 1
                    total += st.st_size
            except OSError as e:  # un archivo que otro proceso acaba de mover: se sigue
                log.warning("no se pudo borrar %s: %s", ruta, e)
    # Carpetas vacías, de abajo hacia arriba, solo a partir del tercer nivel.
    for carpeta, _dirs, _archivos in os.walk(raiz, topdown=False):
        rel = os.path.relpath(carpeta, raiz)
        if rel == "." or os.sep not in rel:
            continue
        try:
            if not os.listdir(carpeta):      # os.walk listó los hijos antes de que se borraran
                os.rmdir(carpeta)
        except OSError:
            pass
    return n, total


def _ruta_sqlite():
    url = db.url()
    if not url.startswith("sqlite:///"):
        return None
    return url[len("sqlite:///"):]


def respaldar_db(conservar=RESPALDOS_CONSERVAR, carpeta=None):
    """Copia la base con `Connection.backup` (consistente aunque haya escrituras
    en curso) a `<carpeta>/creatv_<fecha>.db` y borra las copias más viejas
    que las últimas `conservar`. Devuelve la ruta del respaldo o None si la
    base no es SQLite."""
    ruta = _ruta_sqlite()
    if not ruta or not os.path.exists(ruta):
        return None
    carpeta = carpeta or os.path.join(os.path.dirname(ruta), "respaldos")
    os.makedirs(carpeta, exist_ok=True)
    destino = os.path.join(carpeta, "creatv_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".db")
    origen = sqlite3.connect(ruta)
    try:
        copia = sqlite3.connect(destino)
        try:
            origen.backup(copia)
            # La copia hereda el modo WAL de la base viva; un respaldo tiene que
            # ser UN archivo (sin -wal/-shm al lado) para copiarlo o restaurarlo.
            copia.execute("pragma journal_mode=DELETE")
        finally:
            copia.close()
    finally:
        origen.close()
    for sobra in (destino + "-wal", destino + "-shm"):
        if os.path.exists(sobra):
            os.remove(sobra)
    viejos = sorted(f for f in os.listdir(carpeta) if f.startswith("creatv_") and f.endswith(".db"))
    for nombre in viejos[:-conservar] if conservar > 0 else viejos:
        try:
            os.remove(os.path.join(carpeta, nombre))
        except OSError as e:
            log.warning("no se pudo borrar el respaldo %s: %s", nombre, e)
    return destino


@registrar("salidas_limpiar")
def ejecutar_salidas_limpiar(tarea):
    n, total = limpiar_salidas()
    return gettext("%(n)s archivos borrados de salidas/ (%(mb)s MB).", n=n, mb=f"{total / 1e6:.0f}")


@registrar("cola_limpiar")
def ejecutar_cola_limpiar(tarea):
    n = cola.limpiar_terminadas()
    try:
        from cobros import libro  # noqa: PLC0415
        reservas = libro.limpiar_reservas_muertas()
        if reservas:
            log.info("%s reservas de saldo sin trabajo vivo borradas", reservas)
    except Exception:  # noqa: BLE001 — limpiar reservas no frena la limpieza de la cola
        log.exception("no se pudieron limpiar las reservas de saldo")
    try:
        from cobros import recargas  # noqa: PLC0415
        eventos = recargas.limpiar_eventos_sin_firma()
        if eventos:
            log.info("%s eventos de Bold con firma inválida viejos borrados", eventos)
    except Exception:  # noqa: BLE001 — tampoco frena la limpieza de la cola
        log.exception("no se pudieron limpiar los eventos de Bold sin firma")
    try:
        limpiar_limites()
    except Exception:  # noqa: BLE001 — tampoco frena la limpieza de la cola
        log.exception("no se pudieron limpiar los límites viejos de kv")
    return gettext("%(n)s tareas viejas borradas.", n=n)


def limpiar_limites():
    """S3 (2026-10-08): límites sin marcas vigentes, tras tomar el candado."""
    prefijo = db.kv.c.clave.startswith("limite:", autoescape=True)
    corte = time.time() - 7 * 86400
    with db.conectar() as con:
        con.execute(db.kv.update().where(prefijo).values(valor=db.kv.c.valor))
        filas = con.execute(sa.select(db.kv.c.clave, db.kv.c.valor).where(prefijo)).all()
        borrar = []
        for clave, valor in filas:
            try:
                marcas = json.loads(valor)
                if not isinstance(marcas, list) or not marcas:
                    raise ValueError
                marcas = [float(t) for t in marcas]
                if not all(math.isfinite(t) for t in marcas):
                    raise ValueError
                vieja = max(marcas) < corte
            except (TypeError, ValueError, OverflowError):
                vieja = True
            if vieja:
                borrar.append(clave)
        if borrar:
            con.execute(db.kv.delete().where(db.kv.c.clave.in_(borrar)))
    return len(borrar)


@registrar("db_respaldar")
def ejecutar_db_respaldar(tarea):
    destino = respaldar_db()
    return gettext("Respaldo en %(ruta)s.", ruta=destino) if destino else gettext("La base no es SQLite: sin respaldo.")


@registrar("errores_limpiar")
def ejecutar_errores_limpiar(tarea):
    n = monitoreo.limpiar()
    return gettext("%(n)s errores viejos borrados.", n=n)
