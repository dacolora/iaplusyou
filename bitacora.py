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
