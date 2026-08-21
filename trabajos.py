"""
Trabajos en segundo plano para las acciones lentas del dashboard (generar
prompts, imagen candidata, video, publicar). Evita que el navegador se quede
"colgado" sin avisar nada, y evita que un doble clic dispare la misma acción
dos veces (si ya hay un trabajo en curso con el mismo job_id, no se lanza otro).

Estado en memoria nada más — vive mientras el proceso de dashboard.py esté
arriba. Por eso dashboard.py corre con use_reloader=False: si el auto-reload
matara el proceso a mitad de una generación, esa llamada a Higgsfield se
perdería sin dejar rastro.
"""
import threading
import time

_LOCK = threading.Lock()
_TRABAJOS = {}


def iniciar(job_id, fn, duracion_estimada=60):
    """Lanza fn() en un hilo aparte, salvo que ya haya un trabajo en curso con
    este mismo job_id (entonces no hace nada). Devuelve True si lo lanzó,
    False si ya estaba en curso (ese es el guardado contra doble clic)."""
    with _LOCK:
        existente = _TRABAJOS.get(job_id)
        if existente and existente["estado"] == "en_progreso":
            return False
        _TRABAJOS[job_id] = {
            "estado": "en_progreso",
            "inicio": time.time(),
            "duracion_estimada": duracion_estimada,
            "mensaje": None,
        }

    def _run():
        try:
            mensaje = fn()
            with _LOCK:
                _TRABAJOS[job_id]["estado"] = "completado"
                _TRABAJOS[job_id]["mensaje"] = mensaje or "Listo."
        except Exception as e:
            with _LOCK:
                _TRABAJOS[job_id]["estado"] = "error"
                _TRABAJOS[job_id]["mensaje"] = str(e)

    threading.Thread(target=_run, daemon=True).start()
    return True


def en_curso(job_id):
    with _LOCK:
        t = _TRABAJOS.get(job_id)
        return bool(t and t["estado"] == "en_progreso")


def consultar(job_id):
    """Para el endpoint que el navegador consulta (polling). None si no existe."""
    with _LOCK:
        t = _TRABAJOS.get(job_id)
        if not t:
            return None
        elapsed = time.time() - t["inicio"]
        if t["estado"] == "en_progreso":
            progreso = min(95, int(elapsed / t["duracion_estimada"] * 100))
        else:
            progreso = 100
        return {
            "estado": t["estado"],
            "progreso": progreso,
            "elapsed": int(elapsed),
            "mensaje": t["mensaje"],
        }


def limpiar(job_id):
    with _LOCK:
        _TRABAJOS.pop(job_id, None)
