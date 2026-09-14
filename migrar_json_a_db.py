"""
Importa a la base del motor lo que hoy vive en JSON por cliente:
  clientes/<c>/creative_flow_pendientes.json -> concepto + pieza (via creative_flow)
  clientes/<c>/ads.json                      -> experimento legado + experimento_pieza + metrica_snapshot (via ads)
Idempotente: una entrada cuyo id (cf_.../ad_...) ya está en la base se salta.
Los estados a mitad de camino (cf "video_generando", ad "publicando") entran
como "error" con un mensaje: el hilo que los estaba corriendo ya no existe.
Los JSON no se borran ni se modifican: quedan como respaldo de solo lectura.

Cada entrada se inserta con su id final (legado_id=cf_id/ad_id) desde el
`crear()` inicial — no se renombra en una segunda transacción — así que si el
proceso se cae a mitad de camino, la siguiente corrida la reconoce por ese id
y la salta en vez de duplicarla. La única ventana que queda abierta es entre
el `crear()` y el `actualizar()` de una misma entrada: una caída ahí deja la
fila con los valores por defecto de `crear()` y el resto de campos del JSON
sin aplicar; una corrida posterior la seguirá salteando porque el id ya
existe, así que en ese caso hay que corregirla a mano.

Uso: venv/bin/python3 migrar_json_a_db.py            # todos los clientes
     venv/bin/python3 migrar_json_a_db.py happyflops # uno
"""
import os
import sys

import _json_store
import ads
import creative_flow

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def migrar_cliente(cliente, base_dir=BASE_DIR):
    carpeta = os.path.join(base_dir, "clientes", cliente)
    res = {"conceptos": 0, "anuncios": 0, "saltados": 0}

    cf = _json_store.cargar(os.path.join(carpeta, "creative_flow_pendientes.json"), {})
    existentes = set(creative_flow.cargar(cliente))
    for cf_id, e in cf.items():
        if cf_id in existentes:
            res["saltados"] += 1
            continue
        creative_flow.crear(cliente, e.get("personajes_ids", []), e.get("productos_ids", []),
                            e.get("escenas_ids", []), e.get("accion_central", ""), e.get("duracion_objetivo", 10),
                            e.get("tono", ""), e.get("modo", "A"), referencias_urls=e.get("referencias_urls"),
                            platforms=e.get("platforms"), legado_id=cf_id, creado_en=e.get("creado_en"))
        campos = {k: v for k, v in e.items() if k not in ("creado_en",)}
        if campos.get("estado") == "video_generando":
            # Estaba a mitad de generación en el proceso viejo; nadie la va a terminar.
            campos["estado"] = "error"
            campos["error"] = "Se interrumpió la generación durante la migración. Vuelve a generarla."
        creative_flow.actualizar(cliente, cf_id, **campos)
        res["conceptos"] += 1

    an = _json_store.cargar(os.path.join(carpeta, "ads.json"), {})
    existentes = set(ads.cargar(cliente))
    for ad_id, e in an.items():
        if ad_id in existentes:
            res["saltados"] += 1
            continue
        ads.crear(cliente, e.get("fuente"), e.get("fuente_id"), e.get("contenido_url"),
                 e.get("contenido_tipo"), e.get("nombre"), legado_id=ad_id, creado_en=e.get("creado_en"))
        campos = {k: v for k, v in e.items() if k not in ("fuente", "fuente_id", "contenido_url", "contenido_tipo", "nombre", "creado_en")}
        metricas = campos.pop("metricas", None)
        if campos.get("estado") == "publicando":
            campos["estado"] = "error"
            campos["error"] = ("Se interrumpió la publicación durante la migración. Revisa Ads Manager "
                               "y vuelve a intentar.")
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
