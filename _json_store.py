"""
Helper genérico de lectura/escritura de un JSON por cliente — el mismo patrón
que estado.py, prompts.py, marca.py, conceptos_imagen.py y swaps.py repetían
cada uno por su cuenta (leer si existe, si no devolver un default; escribir
con indent=2, ensure_ascii=False, creando el directorio si hace falta).
"""
import json
import os


def cargar(path, default=None):
    """Lee el JSON. Un archivo vacío o a medio escribir (otro hilo guardando en
    ese instante) devuelve el default en vez de reventar la página."""
    if not os.path.exists(path):
        return {} if default is None else default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, OSError):
        return {} if default is None else default


def guardar(path, data):
    """Escritura atómica: se escribe a un .tmp y se renombra encima. Así ningún
    lector ve nunca un archivo vacío o cortado, aunque haya varios hilos
    (trabajos en segundo plano) guardando el mismo estado."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)
