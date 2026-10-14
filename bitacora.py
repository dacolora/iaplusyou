"""Registro simple de eventos (generación, storage, publicación) en un CSV."""
import csv
import io
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


CAMPOS = ["fecha", "cliente", "id", "etapa", "estado", "detalle"]


def ultimas(limit=200, max_bytes=512_000):
    """Las últimas filas (más recientes primero) leyendo solo el final del archivo: el registro crece sin fin y una
    pantalla del admin no puede leerlo entero en cada visita (auditoría de seguridad de pagos, 2026-10-12)."""
    if not os.path.exists(LOG_FILE):
        return []
    with open(LOG_FILE, "rb") as f:
        f.seek(0, os.SEEK_END)
        tam = f.tell()
        inicio = max(0, tam - int(max_bytes))
        f.seek(inicio)
        datos = f.read().decode("utf-8", "replace")
    if inicio > 0:
        datos = datos.split("\n", 1)[1] if "\n" in datos else ""   # la primera línea puede venir cortada
    filas = [f for f in csv.DictReader(io.StringIO(datos), fieldnames=CAMPOS) if f.get("fecha") != "fecha"]
    return list(reversed(filas))[:limit]
