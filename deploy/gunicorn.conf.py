"""
Configuración de gunicorn del VPS (spec 2026-10-01-escala-y-monitoreo §3).
Antes vivía solo en la unidad de systemd del servidor; aquí queda versionada.
La unidad la usa así (ver deploy/iaplusyou.service):

    ExecStart=/home/deploy/iaplusyou/venv/bin/gunicorn -c deploy/gunicorn.conf.py dashboard:app

Cada valor se puede cambiar sin tocar el archivo con su variable de entorno
(en el `.env`, que la unidad carga con EnvironmentFile).
"""
import os


def _entero(nombre, defecto):
    try:
        return int(os.environ.get(nombre) or defecto)
    except ValueError:
        return defecto


bind = os.environ.get("GUNICORN_BIND", "127.0.0.1:5050")

# UN proceso, a propósito. trabajos.iniciar (pipeline Higgsfield, análisis de
# marca, chat de Flow Plus) guarda el progreso en la memoria del proceso: con
# dos procesos, la barra que sondea /trabajo/<id>/estado caería en el otro y
# vería «desconocido». Los cachés por proceso (tablero, Meta, usuarios) también
# suponen uno. Para usar más CPU hay que mover esos trabajos a la cola primero
# (spec §8, «siguiente paso»). En un VPS de 1 CPU, además, más procesos no dan
# más velocidad: solo más memoria.
workers = 1
worker_class = "gthread"
# Hilos = peticiones atendidas a la vez. Un sondeo de barra dura ~2 ms y la
# página del proyecto ~200 ms de CPU: con más hilos los sondeos no esperan
# detrás de una página. db.opciones_pool da 10 + 10 conexiones: alcanza.
threads = _entero("GUNICORN_HILOS", 16)
# Una página que pasa de 2 min es un error, no una página lenta: se corta y el
# registro de errores (/admin/salud) lo muestra.
timeout = _entero("GUNICORN_TIMEOUT", 120)
# Al reiniciar (despliegue) se espera a que terminen las peticiones en curso.
graceful_timeout = 60
# nginx reutiliza la conexión con gunicorn (keepalive en el upstream).
keepalive = 5
# Nunca reciclar el proceso por número de peticiones: mataría los hilos de
# fondo de trabajos.iniciar a mitad de una generación pagada.
max_requests = 0
# Sin --preload: lo que dashboard.py arranca al importarse (hilos, el engine
# de la base) no debe nacer en el proceso maestro y copiarse con el fork.
preload_app = False

# Registro: a la salida estándar (journald) y, por la app, a data/logs/web.log
# (registro_app.py), que es lo que lee /admin/salud. %(M)s = milisegundos.
accesslog = "-"
access_log_format = '%(h)s "%(r)s" %(s)s %(b)s %(M)sms'
errorlog = "-"
loglevel = "info"
