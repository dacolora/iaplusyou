"""
Cola persistente sobre la tabla `tarea` (db.py). La consumen el worker
(worker.py) y, del lado de gunicorn, trabajos.py para encolar y para leer el
progreso que el navegador consulta. SQLite no tiene SELECT ... FOR UPDATE: el
reclamo es un UPDATE condicionado (WHERE id=? AND estado='pendiente') que solo
gana un proceso.
"""
import re
import threading
import time
from datetime import datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

import db

_RE_TOKEN = re.compile(r"(access_token=)[^&\s\"']+")

# Dedupe de encolar dentro del proceso (gunicorn con hilos). Entre procesos
# manda el índice único parcial uq_tarea_job_viva (db.py / migración 0003).
_ENCOLAR_LOCK = threading.Lock()


def sin_token(texto):
    """Nunca guardar tokens: Meta los mete en paging.next y en mensajes. Solo
    redacta; para acortar (mensajes/errores en la tabla) ver recortar()."""
    return _RE_TOKEN.sub(r"\1***", str(texto or ""))


def recortar(texto, n=500):
    """Corta a n caracteres lo que va a una columna de mensaje/error."""
    return str(texto or "")[:n]


def _fila(r):
    return dict(r._mapping) if r is not None else None


def encolar(tipo, payload, *, cliente=None, job_id=None, duracion_estimada=60, etapas=None,
            ejecutar_desde=None, max_intentos=5):
    """Devuelve el id de la tarea nueva, o None si ya hay una viva (pendiente
    o en_curso) con ese job_id. El chequeo+insert va bajo lock (mismo proceso)
    y el índice único parcial uq_tarea_job_viva cubre la carrera entre
    procesos: si dos pasan el chequeo, el segundo insert falla y devuelve None."""
    ahora = db.ahora()
    with _ENCOLAR_LOCK, db.conectar() as con:
        if job_id:
            viva = con.execute(sa.select(db.tarea.c.id).where(
                db.tarea.c.job_id == job_id, db.tarea.c.estado.in_(("pendiente", "en_curso")))).first()
            if viva:
                return None
        try:
            r = con.execute(db.tarea.insert().values(
                cliente=cliente, job_id=job_id, tipo=tipo, payload=payload or {}, estado="pendiente",
                intentos=0, max_intentos=max_intentos, ejecutar_desde=ejecutar_desde or ahora, creada_en=ahora,
                duracion_estimada=float(duracion_estimada), etapas=[list(e) for e in (etapas or [])],
            ))
        except IntegrityError:
            return None  # otro proceso encoló la misma job_id entre el chequeo y el insert
        return int(r.inserted_primary_key[0])


def reclamar():
    ahora = db.ahora()
    with db.conectar() as con:
        cand = con.execute(sa.select(db.tarea.c.id).where(
            db.tarea.c.estado == "pendiente", db.tarea.c.ejecutar_desde <= ahora
        ).order_by(db.tarea.c.ejecutar_desde, db.tarea.c.id).limit(1)).first()
        if not cand:
            return None
        t0 = time.time()
        r = con.execute(db.tarea.update().where(
            db.tarea.c.id == cand.id, db.tarea.c.estado == "pendiente"
        ).values(estado="en_curso", iniciada_en=ahora, inicio=t0, inicio_etapa=t0,
                 intentos=db.tarea.c.intentos + 1, error=None, indice_etapa=0,
                 progreso_etapa=None, progreso_visto=0.0, detalle=None, etapa_actual=None))
        if r.rowcount != 1:
            return None  # otro proceso ganó; el bucle del worker vuelve a intentar
        return _fila(con.execute(sa.select(db.tarea).where(db.tarea.c.id == cand.id)).first())


def terminar(tarea_id, mensaje=None):
    with db.conectar() as con:
        con.execute(db.tarea.update().where(db.tarea.c.id == tarea_id).values(
            estado="hecha", terminada_en=db.ahora(), mensaje=mensaje or "Listo."))


def fallar(tarea_id, error):
    with db.conectar() as con:
        fila = con.execute(sa.select(db.tarea.c.intentos, db.tarea.c.max_intentos).where(db.tarea.c.id == tarea_id)).first()
        if not fila:
            return
        if fila.intentos < fila.max_intentos:
            espera = timedelta(minutes=2 ** fila.intentos)
            con.execute(db.tarea.update().where(db.tarea.c.id == tarea_id).values(
                estado="pendiente", error=recortar(sin_token(error)),
                ejecutar_desde=(datetime.now() + espera).isoformat(timespec="seconds")))
        else:
            con.execute(db.tarea.update().where(db.tarea.c.id == tarea_id).values(
                estado="error", error=recortar(sin_token(error)), terminada_en=db.ahora(),
                mensaje=recortar(sin_token(error))))


def recuperar_colgadas(minutos=30):
    """Devuelve a `pendiente` (o marca `error` si agotó intentos) lo que lleva
    más de `minutos` en_curso. Con minutos=0 (arranque del worker) toma todo lo
    en_curso, incluso lo iniciado en este mismo segundo — por eso el `<=`."""
    limite = (datetime.now() - timedelta(minutes=minutos)).isoformat(timespec="seconds")
    with db.conectar() as con:
        filas = con.execute(sa.select(db.tarea.c.id, db.tarea.c.intentos, db.tarea.c.max_intentos).where(
            db.tarea.c.estado == "en_curso", db.tarea.c.iniciada_en <= limite)).all()
        tocadas = 0
        for fila in filas:
            if fila.intentos >= fila.max_intentos:
                mensaje = recortar("Se interrumpió (llevaba más de %d min en curso). Revisa el resultado y "
                                   "vuelve a intentar." % minutos)
                con.execute(db.tarea.update().where(db.tarea.c.id == fila.id).values(
                    estado="error", terminada_en=db.ahora(), error=mensaje, mensaje=mensaje))
            else:
                con.execute(db.tarea.update().where(db.tarea.c.id == fila.id).values(
                    estado="pendiente", ejecutar_desde=db.ahora(),
                    error=recortar("recuperada: llevaba más de %d min en curso" % minutos)))
            tocadas += 1
        return tocadas


def reportar(job_id, etapa=None, progreso=None, detalle=None):
    with db.conectar() as con:
        fila = con.execute(sa.select(db.tarea).where(
            db.tarea.c.job_id == job_id, db.tarea.c.estado == "en_curso").order_by(db.tarea.c.id.desc()).limit(1)).first()
        if not fila:
            return
        valores = {}
        if etapa is not None:
            valores["etapa_actual"] = etapa
            nombres = [e[0] for e in (fila.etapas or [])]
            if etapa in nombres and nombres.index(etapa) != (fila.indice_etapa or 0):
                valores.update(indice_etapa=nombres.index(etapa), inicio_etapa=time.time(),
                               progreso_etapa=None, detalle=None)
        if progreso is not None:
            valores["progreso_etapa"] = max(0.0, min(100.0, float(progreso)))
        if detalle is not None:
            valores["detalle"] = detalle
        if valores:
            con.execute(db.tarea.update().where(db.tarea.c.id == fila.id).values(**valores))


def consultar_por_job(job_id):
    with db.conectar() as con:
        return _fila(con.execute(sa.select(db.tarea).where(db.tarea.c.job_id == job_id)
                                 .order_by(db.tarea.c.id.desc()).limit(1)).first())


def consultar_por_id(tarea_id):
    with db.conectar() as con:
        return _fila(con.execute(sa.select(db.tarea).where(db.tarea.c.id == tarea_id)).first())


def actualizar_progreso_visto(tarea_id, valor):
    """La barra nunca retrocede: quien calcula el % (trabajos.consultar) guarda el máximo visto."""
    with db.conectar() as con:
        con.execute(db.tarea.update().where(db.tarea.c.id == tarea_id, db.tarea.c.progreso_visto < valor)
                    .values(progreso_visto=valor))
