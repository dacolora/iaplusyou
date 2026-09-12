"""
Bandeja de referencias de FlowPlus, por cliente: lo que la persona va agregando
(archivos subidos, links descargados, productos del catálogo) antes de generar.
Vive en clientes/<cliente>/referencias_pendientes.json y sobrevive recargas —
así la selección no se pierde cada vez que la página se refresca, que era una
de las quejas del flujo anterior.

Cada referencia: {id, tipo: imagen|video, url, frame_url, etiqueta, origen,
ruta_local?, producto?, logo?, titulo?}. Las etiquetas @Imagen N / @Video N se
recalculan al listar, en orden de llegada, para que nunca queden huecos.
"""
import os
from datetime import datetime

import _json_store

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _path(cliente):
    return os.path.join(BASE_DIR, "clientes", cliente, "referencias_pendientes.json")


def _renumerar(items):
    n_img = n_vid = 0
    for r in items:
        if r.get("tipo") == "video":
            n_vid += 1
            r["etiqueta"] = f"@Video {n_vid}"
        else:
            n_img += 1
            r["etiqueta"] = f"@Imagen {n_img}"
    return items


def listar(cliente):
    return _renumerar(_json_store.cargar(_path(cliente), []) or [])


def _guardar(cliente, items):
    _json_store.guardar(_path(cliente), _renumerar(items))


def agregar(cliente, tipo, url, frame_url=None, origen="archivo", ruta_local=None, titulo=None, producto=None):
    items = listar(cliente)
    rid = "ref_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    items.append({
        "id": rid, "tipo": tipo, "url": url, "frame_url": frame_url or url, "origen": origen,
        "ruta_local": ruta_local, "titulo": titulo, "producto": producto,
        "agregado_en": datetime.now().isoformat(timespec="seconds"),
    })
    _guardar(cliente, items)
    return rid


def quitar(cliente, rid):
    items = [r for r in listar(cliente) if r["id"] != rid]
    _guardar(cliente, items)


def vaciar(cliente):
    _guardar(cliente, [])
