"""
Importa a la base del motor lo que hoy vive en JSON por cliente:
  clientes/<c>/creative_flow_pendientes.json -> concepto + pieza (via creative_flow)
  clientes/<c>/ads.json                      -> experimento legado + experimento_pieza + metrica_snapshot (via ads)
Idempotente: una entrada cuyo id (cf_.../ad_...) ya está en la base se salta.
Los JSON no se borran ni se modifican: quedan como respaldo de solo lectura.

Uso: venv/bin/python3 migrar_json_a_db.py            # todos los clientes
     venv/bin/python3 migrar_json_a_db.py happyflops # uno
"""
import os
import sys

import sqlalchemy as sa

import _json_store
import ads
import creative_flow
import db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _fijar_id_y_fecha(tabla, nuevo_id, legado_id, creado_en):
    # La columna creado_en es String(19); el JSON legado puede traer
    # microsegundos (26 chars) — se trunca. Sin creado_en, se usa db.ahora().
    creado_en = (creado_en or db.ahora())[:19]
    with db.conectar() as con:
        con.execute(tabla.update().where(tabla.c.legado_id == nuevo_id).values(
            legado_id=legado_id, creado_en=creado_en))


def migrar_cliente(cliente, base_dir=BASE_DIR):
    carpeta = os.path.join(base_dir, "clientes", cliente)
    res = {"conceptos": 0, "anuncios": 0, "saltados": 0}

    cf = _json_store.cargar(os.path.join(carpeta, "creative_flow_pendientes.json"), {})
    existentes = set(creative_flow.cargar(cliente))
    for cf_id, e in cf.items():
        if cf_id in existentes:
            res["saltados"] += 1
            continue
        nuevo = creative_flow.crear(cliente, e.get("personajes_ids", []), e.get("productos_ids", []),
                                    e.get("escenas_ids", []), e.get("accion_central", ""), e.get("duracion_objetivo", 10),
                                    e.get("tono", ""), e.get("modo", "A"), referencias_urls=e.get("referencias_urls"),
                                    platforms=e.get("platforms"))
        _fijar_id_y_fecha(db.concepto, nuevo, cf_id, e.get("creado_en"))
        _fijar_id_y_fecha(db.pieza, nuevo, cf_id, e.get("creado_en"))
        campos = {k: v for k, v in e.items() if k not in ("creado_en",)}
        creative_flow.actualizar(cliente, cf_id, **campos)
        res["conceptos"] += 1

    an = _json_store.cargar(os.path.join(carpeta, "ads.json"), {})
    existentes = set(ads.cargar(cliente))
    for ad_id, e in an.items():
        if ad_id in existentes:
            res["saltados"] += 1
            continue
        nuevo = ads.crear(cliente, e.get("fuente"), e.get("fuente_id"), e.get("contenido_url"),
                          e.get("contenido_tipo"), e.get("nombre"))
        _fijar_id_y_fecha(db.experimento_pieza, nuevo, ad_id, e.get("creado_en"))
        campos = {k: v for k, v in e.items() if k not in ("fuente", "fuente_id", "contenido_url", "contenido_tipo", "nombre", "creado_en")}
        metricas = campos.pop("metricas", None)
        ads.actualizar(cliente, ad_id, **campos)
        if metricas and (metricas.get("actualizado_en") or metricas.get("impresiones")):
            ads.actualizar(cliente, ad_id, metricas=metricas)
        res["anuncios"] += 1
    return res


def migrar_todos(base_dir=BASE_DIR):
    raiz = os.path.join(base_dir, "clientes")
    salida = []
    for cliente in sorted(os.listdir(raiz)):
        if os.path.isdir(os.path.join(raiz, cliente)):
            salida.append((cliente, migrar_cliente(cliente, base_dir)))
    return salida


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(sys.argv[1], migrar_cliente(sys.argv[1]))
    else:
        for cliente, r in migrar_todos():
            print(cliente, r)
