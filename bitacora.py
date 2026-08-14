"""Registro simple de eventos (generación, storage, publicación) en un CSV."""
import csv
import os
from datetime import datetime

BASE_DIR = os.path.dirname(__file__)
LOG_FILE = os.path.join(BASE_DIR, "registro_generaciones.csv")


def registrar(cliente, brief_id, etapa, estado, detalle=""):
    write_header = not os.path.exists(LOG_FILE)
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["fecha", "cliente", "id", "etapa", "estado", "detalle"])
        writer.writerow([datetime.now().isoformat(), cliente or "", brief_id, etapa, estado, detalle])


def leer(cliente=None, brief_id=None, limit=200):
    """Lee el CSV y devuelve filas (más recientes primero), filtradas si se pide."""
    if not os.path.exists(LOG_FILE):
        return []
    with open(LOG_FILE, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if cliente is not None:
        rows = [r for r in rows if r.get("cliente") == cliente]
    if brief_id is not None:
        rows = [r for r in rows if r.get("id") == brief_id]
    return list(reversed(rows))[:limit]
