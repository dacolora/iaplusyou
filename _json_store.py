"""
Helper genérico de lectura/escritura de un JSON por cliente — el mismo patrón
que estado.py, prompts.py, marca.py, conceptos_imagen.py y swaps.py repetían
cada uno por su cuenta (leer si existe, si no devolver un default; escribir
con indent=2, ensure_ascii=False, creando el directorio si hace falta).
"""
import json
import os


def cargar(path, default=None):
    if not os.path.exists(path):
        return {} if default is None else default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def guardar(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
