"""
Panel de administrador: lo que el dueño de la plataforma necesita ver de
TODOS los proyectos en una sola pantalla, calculado de solo lectura sobre lo
que cada módulo ya guarda por separado:

- generación del mes (tabla `gasto`, USD) por proyecto y por tipo;
- pauta del mes en Meta por moneda: deltas de acumulados por anuncio, como
  hace el Tablero (`tablero.delta`), pero sobre TODOS los experimentos del
  proyecto, incluido el legado "Anuncios sueltos" (hoy es donde está el
  gasto real);
- piezas generadas en el mes, aprobaciones pendientes (estado_videos.json),
  experimentos corriendo (sin el legado), Meta conectada, tiendas, última
  actividad;
- salud del worker (tabla `tarea`): pendientes, en curso, en error, cuándo
  terminó la última y los últimos errores ya sin tokens;
- historial por mes de los últimos N meses, últimos cobros y el CSV del mes
  con todos los proyectos.

Nada de red: el estado de Meta es lo último guardado en meta.json, no una
llamada, para que el panel abra rápido aunque haya muchos proyectos. Las
rutas viven en dashboard.py (`panel`, `panel_gasto_csv`).
"""
import csv
import io
from datetime import datetime

import sqlalchemy as sa

import cola
import db
import estado
import experimentos
import meta_conexion
import tablero

MESES_HISTORIAL = 6
ULTIMOS_COBROS = 20
ULTIMOS_ERRORES = 5
ESTADOS_PIEZA_GENERADA = ("listo", "degradada")
ENCABEZADO_CSV = ["proyecto", "fecha", "tipo", "proveedor", "referencia", "detalle", "usd"]
_INICIOS_FORMULA = ("=", "+", "-", "@", "\t", "\r")


def _ahora(ahora_iso):
    return (ahora_iso or db.ahora())[:19]


def _inicio_mes(iso):
    return iso[:7] + "-01T00:00:00"


def hace(iso, ahora_iso=None):
    """«hace 5 min» / «hace 3 h» / «hace 2 días»; None sin fecha."""
    if not iso:
        return None
    try:
        t = datetime.fromisoformat(str(iso)[:19])
        ahora = datetime.fromisoformat(_ahora(ahora_iso))
    except ValueError:
        return None
    seg = max(0, int((ahora - t).total_seconds()))
    if seg < 60:
        return "hace un momento"
    if seg < 3600:
        return f"hace {seg // 60} min"
    if seg < 86400:
        return f"hace {seg // 3600} h"
    dias = seg // 86400
    return f"hace {dias} día" + ("s" if dias != 1 else "")


# ------------------------------------------------- generación (tabla gasto) ---

def generacion_mes(clientes, ahora_iso=None):
    """{cliente: {"usd", "cobros", "por_tipo": {tipo: usd}}} del mes en curso,
    en UNA consulta para todos los proyectos."""
    hasta = _ahora(ahora_iso)
    desde = _inicio_mes(hasta)
    out = {c: {"usd": 0.0, "cobros": 0, "por_tipo": {}} for c in clientes}
    if not clientes:
        return out
    g = db.gasto
    q = (sa.select(g.c.cliente, g.c.tipo, sa.func.sum(g.c.usd), sa.func.count())
         .where(g.c.cliente.in_(list(clientes)), g.c.creado_en >= desde, g.c.creado_en <= hasta)
         .group_by(g.c.cliente, g.c.tipo))
    with db.conectar() as con:
        for cliente, tipo, usd, n in con.execute(q):
            d = out[cliente]
            usd = round(float(usd or 0), 4)
            d["por_tipo"][tipo] = usd
            d["usd"] = round(d["usd"] + usd, 4)
            d["cobros"] += int(n)
    return out


# ------------------------------------- pauta (snapshots, incluido el legado) ---

def pauta_mes(clientes, ahora_iso=None):
    """{cliente: {moneda: gasto}} del mes: lo que creció el acumulado de cada
    anuncio dentro del mes (tablero.delta), sumando TODOS los experimentos del
    proyecto, legado incluido. Solo monedas con gasto > 0."""
    hasta = _ahora(ahora_iso)
    desde = _inicio_mes(hasta)
    out = {c: {} for c in clientes}
    if not clientes:
        return out
    ex, ep = db.experimento, db.experimento_pieza
    q = (sa.select(ep.c.id, ex.c.cliente, ex.c.moneda)
         .select_from(ep.join(ex, ep.c.experimento_id == ex.c.id))
         .where(ex.c.cliente.in_(list(clientes))))
    with db.conectar() as con:
        piezas = con.execute(q).fetchall()
    for ep_id, cliente, moneda in piezas:
        snaps = experimentos.snapshots(ep_id, desde=desde)
        if not snaps:
            continue
        gasto = tablero.delta(snaps, desde, hasta, "gasto")
        if gasto <= 0:
            continue
        m = moneda or tablero.MONEDA_POR_DEFECTO
        out[cliente][m] = round(out[cliente].get(m, 0.0) + gasto, 2)
    return out


# ------------------------- piezas, experimentos, conexiones y actividad ---

def piezas_mes(clientes, ahora_iso=None):
    """Piezas generadas (listas o degradadas) creadas en el mes, por proyecto."""
    hasta = _ahora(ahora_iso)
    desde = _inicio_mes(hasta)
    out = {c: 0 for c in clientes}
    if not clientes:
        return out
    p = db.pieza
    q = (sa.select(p.c.cliente, sa.func.count())
         .where(p.c.cliente.in_(list(clientes)), p.c.creado_en >= desde, p.c.creado_en <= hasta,
                p.c.estado.in_(ESTADOS_PIEZA_GENERADA))
         .group_by(p.c.cliente))
    with db.conectar() as con:
        for cliente, n in con.execute(q):
            out[cliente] = int(n)
    return out


def experimentos_corriendo(clientes):
    """Experimentos de verdad en estado corriendo: el legado «Anuncios
    sueltos» siempre está corriendo y no cuenta como experimento."""
    out = {c: 0 for c in clientes}
    if not clientes:
        return out
    ex = db.experimento
    q = (sa.select(ex.c.cliente, sa.func.count())
         .where(ex.c.cliente.in_(list(clientes)), ex.c.legado.is_(False), ex.c.estado == "corriendo")
         .group_by(ex.c.cliente))
    with db.conectar() as con:
        for cliente, n in con.execute(q):
            out[cliente] = int(n)
    return out


def tiendas_conectadas(clientes):
    out = {c: 0 for c in clientes}
    if not clientes:
        return out
    t = db.tienda
    q = sa.select(t.c.cliente, sa.func.count()).where(t.c.cliente.in_(list(clientes))).group_by(t.c.cliente)
    with db.conectar() as con:
        for cliente, n in con.execute(q):
            out[cliente] = int(n)
    return out


def meta_estado(cliente):
    """«conectado» si meta.json guarda un token (lo último que se sabe, sin
    llamar a Meta); si no, «sin_conectar»."""
    datos = meta_conexion.cargar(cliente)
    return "conectado" if datos and datos.get("token") else "sin_conectar"


def ultima_actividad(clientes):
    """Última tarea encolada por proyecto: lo más cercano a «alguien hizo algo»."""
    out = {c: None for c in clientes}
    if not clientes:
        return out
    t = db.tarea
    q = sa.select(t.c.cliente, sa.func.max(t.c.creada_en)).where(t.c.cliente.in_(list(clientes))).group_by(t.c.cliente)
    with db.conectar() as con:
        for cliente, ultimo in con.execute(q):
            out[cliente] = ultimo
    return out


def aprobaciones(clientes):
    """{cliente: {"pendiente", "publicado", "rechazado"}} de estado_videos.json
    (una entrada sin estado cuenta como pendiente), como el panel de siempre."""
    out = {}
    for c in clientes:
        conteo = {"pendiente": 0, "publicado": 0, "rechazado": 0}
        for entry in (estado.cargar(c) or {}).values():
            k = (entry or {}).get("estado") or "pendiente"
            conteo[k] = conteo.get(k, 0) + 1
        out[c] = conteo
    return out


# ------------------------------------------------------------------ worker ---

def salud_worker(ahora_iso=None, n_errores=ULTIMOS_ERRORES):
    """Conteo de tareas por estado, cuándo terminó la última y los últimos
    errores (tipo, proyecto, mensaje sin tokens y recortado)."""
    t = db.tarea
    conteo = {"pendiente": 0, "en_curso": 0, "error": 0, "hecha": 0}
    with db.conectar() as con:
        for est, n in con.execute(sa.select(t.c.estado, sa.func.count()).group_by(t.c.estado)):
            conteo[est] = int(n)
        ultima = con.execute(sa.select(sa.func.max(t.c.terminada_en)).where(t.c.estado == "hecha")).scalar()
        errores = con.execute(
            sa.select(t.c.tipo, t.c.cliente, t.c.terminada_en, t.c.creada_en, t.c.error)
            .where(t.c.estado == "error").order_by(t.c.id.desc()).limit(int(n_errores))).fetchall()
    return {
        "pendientes": conteo["pendiente"], "en_curso": conteo["en_curso"], "error": conteo["error"],
        "hechas": conteo["hecha"], "ultima_hecha": ultima, "ultima_hecha_hace": hace(ultima, ahora_iso),
        "ultimos_errores": [
            {"tipo": e.tipo, "cliente": e.cliente, "cuando": e.terminada_en or e.creada_en,
             "hace": hace(e.terminada_en or e.creada_en, ahora_iso),
             "error": cola.recortar(cola.sin_token(e.error), 200)}
            for e in errores],
    }


# --------------------------------------------------------------- historial ---

def _meses_atras(hasta_iso, n):
    """['2026-09', '2026-08', …]: n meses hacia atrás desde el mes de `hasta`."""
    y, m = int(hasta_iso[:4]), int(hasta_iso[5:7])
    out = []
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out


def gasto_meses(clientes, meses=MESES_HISTORIAL, ahora_iso=None):
    """[{"mes", "por_proyecto": {cliente: usd}, "total"}] del mes en curso
    hacia atrás (el más nuevo primero), en una consulta."""
    hasta = _ahora(ahora_iso)
    lista = _meses_atras(hasta, meses)
    desde = lista[-1] + "-01T00:00:00"
    por_mes = {mes: {c: 0.0 for c in clientes} for mes in lista}
    if clientes:
        g = db.gasto
        mes_de = sa.func.substr(g.c.creado_en, 1, 7)
        q = (sa.select(mes_de, g.c.cliente, sa.func.sum(g.c.usd))
             .where(g.c.cliente.in_(list(clientes)), g.c.creado_en >= desde, g.c.creado_en <= hasta)
             .group_by(mes_de, g.c.cliente))
        with db.conectar() as con:
            for mes, cliente, usd in con.execute(q):
                if mes in por_mes:
                    por_mes[mes][cliente] = round(float(usd or 0), 4)
    return [{"mes": mes, "por_proyecto": por_mes[mes], "total": round(sum(por_mes[mes].values()), 4)}
            for mes in lista]


def _cobro(r):
    d = dict(r._mapping)
    d["usd"] = float(d.get("usd") or 0.0)
    return d


def ultimos_cobros(limite=ULTIMOS_COBROS):
    """Los últimos cobros de todos los proyectos, el más nuevo primero."""
    g = db.gasto
    q = sa.select(g).order_by(g.c.creado_en.desc(), g.c.id.desc()).limit(int(limite))
    with db.conectar() as con:
        return [_cobro(r) for r in con.execute(q)]


def _celda(v):
    """Texto seguro para Excel/Sheets (misma regla que gastos._celda): lo que
    empiece por `=`, `+`, `-`, `@`, tab o CR se evaluaría como fórmula."""
    s = str(v or "")
    return "'" + s if s[:1] in _INICIOS_FORMULA else s


def csv_mes(clientes, ahora_iso=None):
    """CSV (`;`, BOM) con todos los cobros del mes de los proyectos dados:
    las mismas columnas que gastos.csv_mes más la del proyecto."""
    hasta = _ahora(ahora_iso)
    desde = _inicio_mes(hasta)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\n")
    w.writerow(ENCABEZADO_CSV)
    if clientes:
        g = db.gasto
        q = (sa.select(g).where(g.c.cliente.in_(list(clientes)), g.c.creado_en >= desde, g.c.creado_en <= hasta)
             .order_by(g.c.creado_en.asc(), g.c.id.asc()))
        with db.conectar() as con:
            for r in con.execute(q):
                f = _cobro(r)
                w.writerow([_celda(f["cliente"]), _celda(f["creado_en"]), _celda(f["tipo"]), _celda(f.get("proveedor")),
                            _celda(f["referencia"]), _celda(f.get("detalle")), f"{f['usd']:.4f}".replace(".", ",")])
    return "﻿" + buf.getvalue()


# -------------------------------------------------------------- todo junto ---

def resumen(clientes, nombres=None, ahora_iso=None):
    """Lo que pinta el panel: proyectos (uno por cliente, con sus números del
    mes), totales, historial por mes, últimos cobros y salud del worker."""
    clientes = list(clientes or [])
    hasta = _ahora(ahora_iso)
    desde = _inicio_mes(hasta)
    gen = generacion_mes(clientes, hasta)
    pauta = pauta_mes(clientes, hasta)
    piezas = piezas_mes(clientes, hasta)
    exps = experimentos_corriendo(clientes)
    tiendas_ = tiendas_conectadas(clientes)
    actividad = ultima_actividad(clientes)
    aprob = aprobaciones(clientes)
    proyectos = []
    for c in clientes:
        proyectos.append({
            "id": c, "nombre": (nombres or {}).get(c) or c,
            "generacion_usd": gen[c]["usd"], "cobros": gen[c]["cobros"], "por_tipo": gen[c]["por_tipo"],
            "pauta": pauta[c], "piezas_mes": piezas[c],
            "pendiente": aprob[c]["pendiente"], "publicado": aprob[c]["publicado"], "rechazado": aprob[c]["rechazado"],
            "experimentos_corriendo": exps[c], "meta": meta_estado(c), "tiendas": tiendas_[c],
            "ultima_actividad": actividad[c], "ultima_actividad_hace": hace(actividad[c], hasta),
        })
    tot_pauta, tot_tipo = {}, {}
    for p in proyectos:
        for m, v in p["pauta"].items():
            tot_pauta[m] = round(tot_pauta.get(m, 0.0) + v, 2)
        for t, v in p["por_tipo"].items():
            tot_tipo[t] = round(tot_tipo.get(t, 0.0) + v, 4)
    totales = {
        "proyectos": len(proyectos),
        "generacion_usd": round(sum(p["generacion_usd"] for p in proyectos), 4),
        "cobros": sum(p["cobros"] for p in proyectos),
        "por_tipo": tot_tipo, "pauta": tot_pauta,
        "piezas_mes": sum(p["piezas_mes"] for p in proyectos),
        "pendiente": sum(p["pendiente"] for p in proyectos),
        "publicado": sum(p["publicado"] for p in proyectos),
        "rechazado": sum(p["rechazado"] for p in proyectos),
        "experimentos_corriendo": sum(p["experimentos_corriendo"] for p in proyectos),
    }
    return {"desde": desde, "hasta": hasta, "proyectos": proyectos, "totales": totales,
            "meses": gasto_meses(clientes, ahora_iso=hasta), "ultimos_cobros": ultimos_cobros(),
            "worker": salud_worker(hasta)}
