"""¿Se puede reiniciar el worker? Sale con 0 si la cola está vacía y con 1 si hay algo vivo.

Vivo = una tarea `en_curso` o una `pendiente` cuya hora ya llegó. Reiniciar el worker con
una generación pagada a medias la pierde (2026-09-28: un `;` en la cadena del despliegue
reinició el worker con 3 imágenes vivas). Por eso esto corre en un `ssh` PROPIO, antes del
pull y otra vez justo antes del reinicio, y el reinicio solo sigue si devolvió 0:

    ssh deploy@app.creatvmachine.com 'cd /home/deploy/iaplusyou && TZ=America/Bogota venv/bin/python3 deploy/cola_vacia.py' \
      && ssh root@app.creatvmachine.com 'systemctl restart iaplusyou creatv-worker'

Usa sqlite3 directo y no importa la app: tiene que funcionar aunque el código esté a medio
actualizar. Las horas de la cola son locales (db.ahora), de ahí el TZ=America/Bogota.
"""
import os
import sqlite3
import sys
from datetime import datetime

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ruta_base():
    url = os.environ.get("CREATV_DB_URL") or ""
    if url.startswith("sqlite:///"):
        return url[len("sqlite:///"):]
    return os.path.join(RAIZ, "data", "creatv.db")


def vivas(ruta, ahora=None):
    ahora = ahora or datetime.now().isoformat(timespec="seconds")
    con = sqlite3.connect("file:%s?mode=ro" % ruta, uri=True, timeout=10)
    try:
        return con.execute(
            "SELECT id, tipo, cliente, estado, ejecutar_desde FROM tarea "
            "WHERE estado = 'en_curso' OR (estado = 'pendiente' AND ejecutar_desde <= ?) ORDER BY id",
            (ahora,)).fetchall()
    finally:
        con.close()


def main():
    filas = vivas(ruta_base())
    if not filas:
        print("cola vacía: se puede reiniciar")
        return 0
    print("NO reiniciar: %d tarea(s) viva(s)" % len(filas))
    for id_, tipo, cliente, estado, desde in filas:
        print("  %s  %-24s %-16s %-9s desde %s" % (id_, tipo, cliente or "-", estado, desde))
    return 1


if __name__ == "__main__":
    sys.exit(main())
