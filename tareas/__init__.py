"""
Registro de tipos de tarea que ejecuta el worker. Cada módulo de tareas/ se
importa acá para que sus @registrar corran al arrancar el worker.

AL_INTERRUMPIR es el segundo registro: qué hacer con la entidad de dominio
(sesión de Crear, swap, anuncio) cuando recuperar_colgadas marca su tarea en
`error` sin más reintentos — la tarea muere, pero la fila de atrás quedaría
"generando"/"publicando" para siempre si nadie la toca. El hook recibe
`(tarea, mensaje)` y el worker lo envuelve en try/except: nunca tumba el ciclo.
"""
REGISTRO = {}
AL_INTERRUMPIR = {}


def registrar(tipo):
    def _dec(fn):
        REGISTRO[tipo] = fn
        return fn
    return _dec


def al_interrumpir(tipo):
    """Registra `fn(tarea: dict, mensaje: str) -> None` para cuando una tarea
    de ese tipo queda en error por interrupción (reinicio del worker)."""
    def _dec(fn):
        AL_INTERRUMPIR[tipo] = fn
        return fn
    return _dec


def cargar_todas():
    """Importa los módulos con tareas reales. Se llama desde worker.main(), no
    al importar el paquete, para que los tests puedan registrar tareas falsas
    sin arrastrar proveedores externos."""
    from tareas import flowplus, meta, swap  # noqa: F401
