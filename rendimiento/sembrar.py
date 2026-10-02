"""
Datos de carga para medir la plataforma con volumen realista, sin gastar nada
ni tocar R2: N proyectos `<prefijo>NN` con su usuario cliente, M sesiones de
Crear por proyecto (casi todas listas, algunas generando con su tarea viva en
la cola, algunas con error), un gasto por pieza, el historial de tareas que el
worker deja, y dos experimentos por proyecto con diez anuncios y un snapshot de
métricas cada 2 h durante `dias` días (como el refresco periódico). Más un
admin `<prefijo>admin`. Todos con la contraseña `--password`.

    venv/bin/python3 -m rendimiento.sembrar --proyectos 10 --piezas 200
    venv/bin/python3 -m rendimiento.sembrar --limpiar      # borra todo lo sembrado

Usa la base de CREATV_DB_URL (o data/creatv.db), las carpetas `clientes/` y el
`usuarios.json` de ESTE checkout. Se niega si PLATAFORMA_URL (del entorno o del
.env raíz) apunta a otra máquina: nunca siembra en producción. Lo mejor es
correrlo en una copia aparte del repositorio (ver rendimiento/README.md).
"""
import argparse
import os
import random
import shutil
import sys
import time
from datetime import datetime, timedelta
from urllib.parse import urlsplit

import sqlalchemy as sa

import _json_store
import catalogo_productos
import db
import flowplus_lanzar
import proyectos
import usuarios

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASSWORD = "carga-1234"
PREFIJO = "carga"
HOSTS_LOCALES = ("", "localhost", "127.0.0.1", "::1")
MODELOS = ("wan3", "kling_o3_pro", "seedance_25")
COLORES = ("negro", "beige", "rosa")
PROMPT = ("A close-up of the product on a sunlit wooden table, slow dolly-in, soft morning light, "
          "a hand enters the frame and picks it up, shallow depth of field, warm tones. ") * 3


def _plataforma_url():
    valor = os.environ.get("PLATAFORMA_URL")
    if valor is None:
        try:
            with open(os.path.join(BASE, ".env"), encoding="utf-8") as f:
                for linea in f:
                    if linea.strip().startswith("PLATAFORMA_URL="):
                        valor = linea.split("=", 1)[1].strip().strip("'\"")
        except OSError:
            valor = ""
    return valor or ""


def es_local():
    """True si PLATAFORMA_URL no está o apunta a esta máquina."""
    host = (urlsplit(_plataforma_url()).hostname or "").lower()
    return host in HOSTS_LOCALES


def nombres(proyectos_n, prefijo=PREFIJO):
    return [f"{prefijo}{i:02d}" for i in range(1, proyectos_n + 1)]


def _iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%S")


def _usuarios(clientes, prefijo, password):
    datos = usuarios.cargar()
    hash_ = usuarios._hash(password)
    ahora = db.ahora()
    for c in clientes:
        datos[c] = {"password_hash": hash_, "rol": "cliente", "cliente": c, "correo": f"{c}@carga.local",
                    "correo_verificado": True, "session_version": 1, "creado_en": ahora, "idioma": "es"}
    datos[f"{prefijo}admin"] = {"password_hash": hash_, "rol": "admin", "cliente": None,
                                "correo": f"{prefijo}admin@carga.local", "correo_verificado": True,
                                "session_version": 1, "creado_en": ahora, "idioma": "es"}
    usuarios.guardar(datos)


def _catalogo(cliente, productos_n, rnd):
    """Catálogo en disco como el de un proyecto real: `productos_n` productos
    con 3 colores y 4 fotos cada uno (JPEG de 8×8) y su productos.json.
    Devuelve los nombres visibles de los colores (lo que Crear guarda en
    `productos_ids`)."""
    from PIL import Image
    carpeta = os.path.join(BASE, "clientes", cliente, catalogo_productos.CATEGORIAS["producto"]["carpeta"])
    foto = Image.new("RGB", (8, 8), (200, 120, 90))
    meta, nombres_colores = {}, []
    for i in range(productos_n):
        pid = f"producto_{i:02d}"
        variantes = {}
        for color in COLORES:
            os.makedirs(os.path.join(carpeta, pid, color), exist_ok=True)
            for k in range(4):
                foto.save(os.path.join(carpeta, pid, color, f"{color}_{k}.jpg"))
            nombre = f"Producto {i} {color.title()}"
            variantes[color] = {"nombre": nombre, "disponible": True}
            nombres_colores.append(nombre)
        foto.save(os.path.join(carpeta, pid, "ambiente.jpg"))
        meta[pid] = {"nombre": f"Producto {i}", "descripcion": "Sandalia de prueba.", "variantes": variantes}
    catalogo_productos.guardar_meta(cliente, meta, "producto")
    return nombres_colores


def _crear(con, cliente, piezas, rnd, inicio, nombres_colores=()):
    """Sesiones de Crear: concepto + pieza como las deja creative_flow (en
    bloque, mucho más rápido que llamar a crear/actualizar una por una).
    Devuelve [(pieza_id, cf_id, estado)]."""
    conceptos, piezas_filas = [], []
    for i in range(piezas):
        t = inicio + timedelta(minutes=37 * i)
        cf_id = f"cf_{t.strftime('%Y%m%d_%H%M%S')}_{i:06d}"
        r = rnd.random()
        estado = "video_listo" if r < 0.85 else ("error" if r < 0.95 else "video_generando")
        conceptos.append({
            "cliente": cliente, "creado_en": _iso(t), "actualizado_en": _iso(t), "origen": "manual",
            "legado_id": cf_id, "enfoque": "producto",
            "extra": {"personajes_ids": [], "escenas_ids": [],
                      # La mitad nombra un color del catálogo; la otra, un producto que ya no está.
                      "productos_ids": [rnd.choice(nombres_colores)] if nombres_colores and i % 2 else ["Sandalia vieja"],
                      "accion_central": f"Idea de prueba {i}", "duracion_objetivo": 8, "tono": "cálido", "modo": "A",
                      "platforms": [], "prompt_relleno": PROMPT, "referencias_urls": [
                          f"https://example.invalid/{cliente}/ref_{i}_1.jpg", f"https://example.invalid/{cliente}/ref_{i}_2.jpg"],
                      "estado_legado": estado, "titulo": f"Pieza {i}", "con_sonido": True},
        })
    res = con.execute(db.concepto.insert().returning(db.concepto.c.id, db.concepto.c.legado_id), conceptos).all()
    for (cid, cf_id), c in zip(res, conceptos):
        estado = c["extra"]["estado_legado"]
        listo = estado == "video_listo"
        piezas_filas.append({
            "cliente": cliente, "creado_en": c["creado_en"], "actualizado_en": c["creado_en"], "concepto_id": cid,
            "tipo": "video", "estado": {"video_listo": "listo", "error": "error"}.get(estado, "generando"),
            "modelo": rnd.choice(MODELOS), "duracion_s": 8.0, "aspect_ratio": "9:16", "legado_id": cf_id,
            "url_video": f"https://example.invalid/{cliente}/{cf_id}.mp4" if listo else None,
            "costo_usd": 0.6 if listo else None, "error": "El proveedor rechazó el pedido." if estado == "error" else None,
            "capas": {"sonido": {"proveedor": "wan3", "estado": "ok"}} if listo else {}, "extra": {},
        })
    pids = con.execute(db.pieza.insert().returning(db.pieza.c.id), piezas_filas).scalars().all()
    return [(pid, c["legado_id"], c["extra"]["estado_legado"]) for pid, c in zip(pids, conceptos)]


def _gastos_y_tareas(con, cliente, sesiones, inicio):
    gastos, tareas = [], []
    for k, (pid, cf_id, estado) in enumerate(sesiones):
        t = _iso(inicio + timedelta(minutes=37 * k + 5))
        job = flowplus_lanzar.job_id(cliente, cf_id)     # el mismo que sondea la tarjeta
        if estado == "video_listo":
            gastos.append({"cliente": cliente, "creado_en": t, "tipo": "video", "usd": 0.6, "proveedor": "wavespeed",
                           "referencia": f"video:{cf_id}:t{k}", "detalle": "wan3 8 s", "extra": {}})
        base = {"cliente": cliente, "tipo": "flowplus_video", "payload": {"cliente": cliente, "cf_id": cf_id},
                "max_intentos": 1, "prioridad": 5, "ejecutar_desde": t, "creada_en": t, "duracion_estimada": 240.0,
                "etapas": [["Generando", 90], ["Mezclando sonido", 10]], "intentos": 1}
        if estado == "video_generando":
            tareas.append({**base, "job_id": job, "estado": "en_curso", "iniciada_en": t, "inicio": time.time() - 60,
                           "etapa_actual": "Generando", "indice_etapa": 0, "inicio_etapa": time.time() - 60})
        else:
            tareas.append({**base, "job_id": job, "estado": "hecha" if estado == "video_listo" else "error",
                           "iniciada_en": t, "terminada_en": t,
                           "error": "El proveedor rechazó el pedido." if estado == "error" else None})
    # Las periódicas del worker: una fila por vuelta (antes de limpiar_terminadas).
    for k in range(200):
        t = _iso(inicio + timedelta(minutes=5 * k))
        tareas.append({"cliente": None, "job_id": f"periodica__exp_decidir_todos__{cliente}{k}", "tipo": "exp_decidir_todos",
                       "payload": {}, "estado": "hecha", "max_intentos": 1, "prioridad": 5, "ejecutar_desde": t,
                       "creada_en": t, "iniciada_en": t, "terminada_en": t, "intentos": 1})
    if gastos:
        con.execute(db.gasto.insert(), gastos)
    con.execute(db.tarea.insert(), _uniformes(tareas))


def _uniformes(filas):
    """Las mismas claves en todas las filas (un insert en bloque las exige):
    lo que una fila no trae va como None."""
    claves = set().union(*filas)
    return [{k: f.get(k) for k in claves} for f in filas]


def _experimentos(con, cliente, sesiones, dias, rnd, inicio):
    listas = [s for s in sesiones if s[2] == "video_listo"]
    for e in range(2):
        t0 = inicio + timedelta(days=e * 3)
        eid = con.execute(db.experimento.insert().values(
            cliente=cliente, creado_en=_iso(t0), actualizado_en=_iso(t0), nombre=f"Prueba {e + 1}", modo="semi",
            paises=[{"pais": "CO", "idioma": "es", "presupuesto_dia": 40000}], moneda="COP", tope_total=1_000_000,
            dias=dias, objetivo_meta="OUTCOME_TRAFFIC", atribucion="ninguna", estado="corriendo",
            meta_campaign_id=f"23800000000{e}", legado=False, destino_url="https://example.invalid/tienda",
            extra={})).inserted_primary_key[0]
        snapshots, eventos = [], []
        for j, (pid, cf_id, _) in enumerate(listas[e * 10:(e + 1) * 10]):
            epid = con.execute(db.experimento_pieza.insert().values(
                cliente=cliente, creado_en=_iso(t0), actualizado_en=_iso(t0), experimento_id=eid, pieza_id=pid,
                pais="CO", meta_ad_id=f"2390000{e}{j:04d}", estado="activo", estado_meta="ACTIVE",
                veredicto=rnd.choice(("pendiente", "ganador", "perdedor", "inconcluso")), extra={})).inserted_primary_key[0]
            imp = gasto = clics = 0
            for h in range(dias * 12):
                imp += rnd.randint(50, 400)
                clics += rnd.randint(0, 8)
                gasto += rnd.uniform(500, 3000)
                snapshots.append({"experimento_pieza_id": epid, "tomado_en": _iso(t0 + timedelta(hours=2 * h)),
                                  "impresiones": imp, "alcance": int(imp * 0.8), "frecuencia": 1.25, "clics": clics,
                                  "clics_enlace": clics, "ctr": clics / imp * 100, "cpc": gasto / max(clics, 1),
                                  "cpm": gasto / imp * 1000, "thruplay": int(imp * 0.2), "thruplay_rate": 20.0,
                                  "gasto": round(gasto, 2), "fuente_ventas": "ninguna", "extra": {}})
            for k in range(25):
                eventos.append({"cliente": cliente, "experimento_id": eid, "experimento_pieza_id": epid, "tipo": "veredicto",
                                "mensaje": f"Veredicto {k}", "datos": {}, "creado_en": _iso(t0 + timedelta(hours=k))})
        if snapshots:
            con.execute(db.metrica_snapshot.insert(), snapshots)
            con.execute(db.evento.insert(), eventos)


def sembrar(proyectos_n=10, piezas=200, dias=14, prefijo=PREFIJO, password=PASSWORD, semilla=7, productos=25):
    """Siembra y devuelve la lista de proyectos. Idempotente por proyecto: uno
    que ya tenga sesiones de Crear no se vuelve a sembrar."""
    rnd = random.Random(semilla)
    clientes = nombres(proyectos_n, prefijo)
    _usuarios(clientes, prefijo, password)
    inicio = datetime.now() - timedelta(days=max(dias, piezas * 37 // 1440 + 1))
    for c in clientes:
        _json_store.guardar(proyectos._path(c), {"nombre": c.capitalize(), "idioma": "es", "pais": "CO"})
        with db.conectar() as con:
            ya = con.execute(sa.select(sa.func.count()).select_from(db.concepto)
                             .where(db.concepto.c.cliente == c)).scalar()
            if ya:
                continue
            sesiones = _crear(con, c, piezas, rnd, inicio, _catalogo(c, productos, rnd) if productos else ())
            _gastos_y_tareas(con, c, sesiones, inicio)
            _experimentos(con, c, sesiones, dias, rnd, inicio)
    return clientes


TABLAS_POR_CLIENTE = ("gasto", "tarea", "evento", "propuesta", "pieza", "concepto")


def limpiar(prefijo=PREFIJO):
    """Borra lo sembrado: filas de la base cuyo cliente empieza por el prefijo,
    sus carpetas en clientes/ y sus usuarios."""
    patron = f"{prefijo}%"
    with db.conectar() as con:
        ep = sa.select(db.experimento_pieza.c.id).where(db.experimento_pieza.c.cliente.like(patron))
        con.execute(db.metrica_snapshot.delete().where(db.metrica_snapshot.c.experimento_pieza_id.in_(ep)))
        con.execute(db.metrica_dia.delete().where(db.metrica_dia.c.experimento_pieza_id.in_(ep)))
        con.execute(db.metrica_desglose.delete().where(db.metrica_desglose.c.experimento_pieza_id.in_(ep)))
        con.execute(db.evento.delete().where(db.evento.c.cliente.like(patron)))
        con.execute(db.experimento_pieza.delete().where(db.experimento_pieza.c.cliente.like(patron)))
        con.execute(db.experimento.delete().where(db.experimento.c.cliente.like(patron)))
        for nombre in TABLAS_POR_CLIENTE:
            tabla = db.metadata.tables[nombre]
            con.execute(tabla.delete().where(tabla.c.cliente.like(patron)))
        con.execute(db.tarea.delete().where(db.tarea.c.job_id.like(f"periodica__exp_decidir_todos__{patron}")))
    carpeta = os.path.join(BASE, "clientes")
    for nombre in os.listdir(carpeta) if os.path.isdir(carpeta) else ():
        if nombre.startswith(prefijo) and os.path.isfile(os.path.join(carpeta, nombre, "proyecto.json")):
            shutil.rmtree(os.path.join(carpeta, nombre))
    datos = usuarios.cargar()
    usuarios.guardar({u: e for u, e in datos.items() if not u.startswith(prefijo)})


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--proyectos", type=int, default=10)
    p.add_argument("--piezas", type=int, default=200, help="sesiones de Crear por proyecto")
    p.add_argument("--dias", type=int, default=14, help="días de snapshots de métricas")
    p.add_argument("--productos", type=int, default=25, help="productos del catálogo (3 colores, 4 fotos)")
    p.add_argument("--prefijo", default=PREFIJO)
    p.add_argument("--password", default=PASSWORD)
    p.add_argument("--limpiar", action="store_true", help="borra lo sembrado con ese prefijo")
    a = p.parse_args(argv)
    if not es_local():
        sys.exit(f"PLATAFORMA_URL apunta a {_plataforma_url()}: esto solo siembra en una máquina local.")
    if a.limpiar:
        limpiar(a.prefijo)
        print(f"Borrado lo sembrado con el prefijo «{a.prefijo}».")
        return
    db.crear_todo()
    clientes = sembrar(a.proyectos, a.piezas, a.dias, a.prefijo, a.password, productos=a.productos)
    print(f"Sembrados {len(clientes)} proyectos ({clientes[0]}…{clientes[-1]}), usuarios con la contraseña "
          f"«{a.password}» y el admin «{a.prefijo}admin».")


if __name__ == "__main__":
    main()
