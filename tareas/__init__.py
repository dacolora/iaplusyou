"""
Registro de tipos de tarea que ejecuta el worker. Cada módulo de tareas/ se
importa acá para que sus @registrar corran al arrancar el worker.
"""
REGISTRO = {}


def registrar(tipo):
    def _dec(fn):
        REGISTRO[tipo] = fn
        return fn
    return _dec


def cargar_todas():
    """Importa los módulos con tareas reales. Se llama desde worker.main(), no
    al importar el paquete, para que los tests puedan registrar tareas falsas
    sin arrastrar proveedores externos."""
    from tareas import flowplus, meta, swap  # noqa: F401
