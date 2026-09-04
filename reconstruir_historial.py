"""
Reconstruye en swaps.json las generaciones que la bitácora prueba que ocurrieron
pero que ya no están en el estado (se borraron desde la interfaz).

Qué es esto y qué NO es
-----------------------
La bitácora (registro_generaciones.csv) es append-only: cada generación que
terminó bien dejó una fila con fecha, hora, cliente, id del swap y la ruta del
archivo resultante. Esa fila es evidencia primaria de que la generación existió.
Este script la usa para volver a crear la entrada correspondiente.

Lo que SÍ se reconstruye, porque está probado en la bitácora:
  - que la generación ocurrió y terminó bien
  - su fecha y hora exactas
  - su id y la ruta del archivo que produjo

Lo que NO se reconstruye, porque la bitácora no lo guarda:
  - el costo (usd/credits)  -> queda en None, NO se estima
  - el producto y el modelo -> quedan en None
Rellenar esos campos con números plausibles sería inventar datos financieros.
Se marcan como desconocidos y la UI los muestra así.

Cada entrada reconstruida lleva origen="reconstruido_desde_bitacora" para que
nunca se confunda con una registrada en vivo.

Uso:
    venv/bin/python3 reconstruir_historial.py            # muestra qué haría
    venv/bin/python3 reconstruir_historial.py --aplicar  # lo escribe
"""
import os
import shutil
import sys
from datetime import datetime

import bitacora
import swaps as swaps_mod

BASE_DIR = os.path.dirname(__file__)
ORIGEN = "reconstruido_desde_bitacora"


def huerfanos(cliente):
    """Swaps que la bitácora vio terminar bien y que ya no están en swaps.json."""
    actuales = swaps_mod.cargar(cliente)
    vistos = set()
    resultado = []
    for e in bitacora.leer(limit=100000):
        if e.get("etapa") != "swap" or e.get("estado") != "ok":
            continue
        if e.get("cliente") != cliente:
            continue
        swap_id = e.get("id")
        if not swap_id or swap_id in actuales or swap_id in vistos:
            continue
        vistos.add(swap_id)
        ruta = e.get("detalle") or ""
        resultado.append({
            "id": swap_id,
            "fecha": e.get("fecha"),
            "ruta": ruta,
            "en_disco": bool(ruta) and os.path.exists(ruta),
        })
    return resultado


def entrada_reconstruida(h):
    """Una entrada con la MISMA forma que crea swaps.crear(), pero con los campos
    que no se pueden probar en None y una marca de origen."""
    en_disco = h["en_disco"]
    return {
        "foto_original_local": None,       # la bitácora no guarda la foto de entrada
        "producto_id": None,               # desconocido
        "aspect_ratio": None,
        "proveedor": None,                 # desconocido
        "tipo": "foto" if h["ruta"].endswith(".png") else "video",
        "estado": "listo",
        "resultado_url": None,             # si se subió a R2, esa URL se perdió
        "resultado_local": h["ruta"] if en_disco else None,
        "credits": None,
        "usd": None,                       # NO se estima: no está registrado
        "evaluacion": None,
        "evaluacion_estado": None,
        "error": None,
        "creado_en": h["fecha"],
        "origen": ORIGEN,
        "archivo_disponible": en_disco,
    }


def reconstruir(cliente, aplicar=False):
    pendientes = huerfanos(cliente)
    if not pendientes:
        print(f"[{cliente}] no hay generaciones huérfanas: el estado ya coincide con la bitácora.")
        return 0

    con_archivo = sum(1 for h in pendientes if h["en_disco"])
    print(f"[{cliente}] {len(pendientes)} generaciones probadas por la bitácora que faltan en swaps.json")
    print(f"          {con_archivo} conservan su archivo en disco, {len(pendientes) - con_archivo} no.\n")
    for h in pendientes:
        marca = "con archivo" if h["en_disco"] else "solo registro"
        print(f"  {h['fecha'][:19]}  {h['id']}  ({marca})")

    if not aplicar:
        print("\n(simulación — corre con --aplicar para escribirlo)")
        return len(pendientes)

    data = swaps_mod.cargar(cliente)
    ruta_json = os.path.join(BASE_DIR, "clientes", cliente, "swaps.json")
    if os.path.exists(ruta_json):
        respaldo = f"{ruta_json}.respaldo_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(ruta_json, respaldo)
        print(f"\nRespaldo: {respaldo}")

    for h in pendientes:
        data[h["id"]] = entrada_reconstruida(h)
    swaps_mod.guardar(cliente, data)
    print(f"Reconstruidas {len(pendientes)} entradas en swaps.json (marcadas como '{ORIGEN}').")
    return len(pendientes)


if __name__ == "__main__":
    aplicar = "--aplicar" in sys.argv
    clientes_dir = os.path.join(BASE_DIR, "clientes")
    for cli in sorted(os.listdir(clientes_dir)):
        if os.path.isdir(os.path.join(clientes_dir, cli)):
            reconstruir(cli, aplicar=aplicar)
