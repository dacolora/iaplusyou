"""Copias de Meta en la base y sus lecturas agregadas (spec §4, §6 y §8). Único
escritor de meta_cuenta_dia, meta_anuncio_dia, meta_objeto y meta_alcance.

Cada escritura es UNA transacción. Reemplazar un tramo borra ese rango de la
cuenta y lo vuelve a escribir: Meta reatribuye compras de días pasados, así
que la copia de los últimos 7 días siempre pisa lo anterior. Cada lectura es
UNA consulta agregada (la pestaña nunca hace una consulta por fila): filtra por
proyecto + cuentas + fechas, así que usa el índice (cliente, cuenta, fecha), y
una lista de cuentas vacía devuelve vacío sin tocar la base."""
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite import insert as insert_sqlite

import db

METRICAS = ("gasto", "impresiones", "clics", "clics_salida", "compras", "valor", "vistas_3s", "thruplays")
METRICAS_CUENTA = METRICAS + ("alcance",)
METRICAS_ANUNCIO = METRICAS + ("p25", "p50", "p75", "p100")
_ENTEROS = {"impresiones", "alcance", "clics", "clics_salida", "vistas_3s", "thruplays", "p25", "p50", "p75", "p100"}

# Columnas de meta_objeto que escribe el llamador (el resto las pone esta capa).
_COLUMNAS_OBJETO = ("nivel", "padre_id", "campaign_id", "nombre", "estado", "objetivo", "optimizacion",
                    "presupuesto_diario", "presupuesto_total", "estrategia_puja", "aprendizaje", "creative_id",
                    "miniatura_url", "video_id", "creado_en_meta", "extra")
_NIVELES = ("campana", "conjunto", "anuncio")
# Un NOT IN / IN con miles de ids no cabe en el tope de variables de SQLite: se parte en tandas.
_TANDA_IDS = 500


# ------------------------------------------------------------ números ---

def _entero(v):
    return int(float(v or 0))


def _monto(v):
    return float(v or 0)


def _valor(columna, v):
    return _entero(v) if columna in _ENTEROS else _monto(v)


def _medidas(fila, columnas):
    """Las sumas/valores de una fila agregada con el tipo de cada medida (int o float)."""
    return {c: _valor(c, fila[c]) for c in columnas}


def _con_alias_evaluacion(d):
    """`triple_whale.evaluacion.metricas` lee `pedidos` e `ingresos`: en Meta son `compras` y `valor`."""
    d["pedidos"] = d["compras"]
    d["ingresos"] = d["valor"]
    return d


# ------------------------------------------------------------ escribir ---

def _reemplazar(tabla, columnas, cliente, act, desde, hasta, filas, llave):
    """Borra [desde, hasta] de esa cuenta y escribe `filas` (las de fuera del rango se ignoran) en una
    transacción. Si la misma `llave` llega dos veces en la tanda (solape al paginar), gana la última."""
    ahora = db.ahora()
    por_llave = {}
    for f in filas or []:
        fecha = str(f.get("fecha") or "")[:10]
        if not (desde <= fecha <= hasta):
            continue
        nueva = {"cliente": cliente, "ad_account_id": act, "fecha": fecha, "actualizado_en": ahora}
        nueva.update({c: _valor(c, f.get(c)) for c in columnas})
        for c in ("campaign_id", "adset_id", "ad_id"):
            if c in tabla.c:
                nueva[c] = None if f.get(c) is None else str(f[c])
        k = llave(nueva)
        if k is None:
            continue
        por_llave[k] = nueva
    registros = list(por_llave.values())
    with db.conectar() as con:
        con.execute(tabla.delete().where(tabla.c.cliente == cliente, tabla.c.ad_account_id == act,
                                         tabla.c.fecha >= desde, tabla.c.fecha <= hasta))
        if registros:
            con.execute(tabla.insert(), registros)
    return len(registros)


def reemplazar_cuenta_dias(cliente, act, desde, hasta, filas):
    """La cuenta por día para [desde, hasta]: borra el rango de ESA cuenta y lo vuelve a escribir.
    Claves de fila: fecha, gasto, impresiones, alcance, clics, clics_salida, compras, valor, vistas_3s, thruplays.
    Devuelve cuántas filas escribió."""
    return _reemplazar(db.meta_cuenta_dia, METRICAS_CUENTA, cliente, act, desde, hasta, filas,
                       llave=lambda r: r["fecha"])


def reemplazar_anuncio_dias(cliente, act, desde, hasta, filas):
    """El anuncio por día para [desde, hasta]: borra el rango de ESA cuenta y lo vuelve a escribir.
    Claves de fila: fecha, campaign_id, adset_id, ad_id y METRICAS_ANUNCIO. Una fila sin `ad_id` se ignora.
    Devuelve cuántas filas escribió."""
    return _reemplazar(db.meta_anuncio_dia, METRICAS_ANUNCIO, cliente, act, desde, hasta, filas,
                       llave=lambda r: (r["ad_id"], r["fecha"]) if r.get("ad_id") else None)


def guardar_objetos(cliente, act, objetos):
    """Upsert por (cliente, objeto_id) de campañas, conjuntos y anuncios. Solo se actualizan las columnas
    PRESENTES en cada dict: un objeto que llega solo con su nombre (viene de los insights, sin «estado») no borra
    el estado, el presupuesto, el aprendizaje ni la miniatura ya guardados. Un `nombre` None tampoco pisa el
    guardado. Claves: `nivel`, `objeto_id` y las columnas de meta_objeto (sin id/cliente/ad_account_id/
    actualizado_en). Los objetos con el mismo juego de claves se escriben juntos en una tanda. Devuelve cuántos."""
    t = db.meta_objeto
    ahora = db.ahora()
    grupos = {}
    for o in objetos or []:
        if not o.get("objeto_id") or o.get("nivel") not in _NIVELES:
            continue
        valores = {c: o[c] for c in _COLUMNAS_OBJETO if c in o}
        valores["objeto_id"] = str(o["objeto_id"])
        grupos.setdefault(frozenset(valores), []).append(valores)
    n = 0
    with db.conectar() as con:
        for claves, lote in grupos.items():
            filas = [dict(v, cliente=cliente, ad_account_id=act, actualizado_en=ahora,
                          **({} if "extra" in claves else {"extra": {}})) for v in lote]
            nuevo = insert_sqlite(t)
            set_ = {c: getattr(nuevo.excluded, c) for c in claves if c not in ("objeto_id", "extra")}
            if "extra" in claves:
                set_["extra"] = nuevo.excluded.extra
            if "nombre" in claves:
                set_["nombre"] = sa.func.coalesce(nuevo.excluded.nombre, t.c.nombre)
            set_["ad_account_id"] = nuevo.excluded.ad_account_id
            set_["actualizado_en"] = nuevo.excluded.actualizado_en
            con.execute(nuevo.on_conflict_do_update(index_elements=["cliente", "objeto_id"], set_=set_), filas)
            n += len(filas)
    return n


def marcar_sin_estado(cliente, act, nivel, vistos):
    """Pone `estado=None` a los objetos del nivel que Meta ya no devolvió (archivados o borrados): se
    distinguen de los que siguen ahí. Devuelve cuántos cambió."""
    t = db.meta_objeto
    vistos = {str(v) for v in vistos or ()}
    ahora = db.ahora()
    cond = (t.c.cliente == cliente, t.c.ad_account_id == act, t.c.nivel == nivel)
    with db.conectar() as con:
        guardados = con.execute(sa.select(t.c.objeto_id).where(*cond, t.c.estado.is_not(None))).scalars().all()
        faltan = [i for i in guardados if i not in vistos]
        n = 0
        for i in range(0, len(faltan), _TANDA_IDS):
            n += con.execute(t.update().where(*cond, t.c.objeto_id.in_(faltan[i:i + _TANDA_IDS]))
                             .values(estado=None, actualizado_en=ahora)).rowcount
    return n


def guardar_alcance(cliente, act, filas):
    """Alcance y frecuencia de una ventana (gente única: no se suma por días). Upsert por
    (cliente, objeto_id, ventana). Claves: nivel, objeto_id, ventana, alcance, frecuencia. Devuelve cuántas."""
    t = db.meta_alcance
    ahora = db.ahora()
    registros = [dict(cliente=cliente, ad_account_id=act, nivel=f["nivel"], objeto_id=str(f["objeto_id"]),
                      ventana=int(f["ventana"]), alcance=_entero(f.get("alcance")),
                      frecuencia=None if f.get("frecuencia") is None else float(f["frecuencia"]),
                      calculado_en=ahora) for f in filas or []]
    if not registros:
        return 0
    nuevo = insert_sqlite(t)
    set_ = {c: getattr(nuevo.excluded, c) for c in ("ad_account_id", "nivel", "alcance", "frecuencia", "calculado_en")}
    with db.conectar() as con:
        con.execute(nuevo.on_conflict_do_update(index_elements=["cliente", "objeto_id", "ventana"], set_=set_),
                    registros)
    return len(registros)


def borrar_cuenta(cliente, act):
    """Quita las cuatro copias de esa cuenta en ese proyecto (nunca `meta_cuenta` ni lo de otro proyecto)."""
    with db.conectar() as con:
        for t in (db.meta_cuenta_dia, db.meta_anuncio_dia, db.meta_objeto, db.meta_alcance):
            con.execute(t.delete().where(t.c.cliente == cliente, t.c.ad_account_id == act))


def purgar_anuncios(antes_de):
    """Borra los días de anuncio anteriores a `antes_de` (AAAA-MM-DD) de todos los proyectos: la copia
    guarda 90 días. Devuelve cuántas filas quitó."""
    t = db.meta_anuncio_dia
    with db.conectar() as con:
        return con.execute(t.delete().where(t.c.fecha < antes_de)).rowcount


# -------------------------------------------------------------- leer ---

def _donde(t, cliente, cuentas, desde, hasta):
    return (t.c.cliente == cliente, t.c.ad_account_id.in_(list(cuentas)), t.c.fecha >= desde, t.c.fecha <= hasta)


def _sumas(t, columnas):
    return [sa.func.sum(t.c[c]).label(c) for c in columnas]


def rango(cliente, cuentas):
    """Cuántos días de cuenta hay copiados y de qué fecha a qué fecha (para el aviso «sin datos» y el borde
    del selector de período)."""
    vacio = {"filas": 0, "desde": None, "hasta": None}
    if not cuentas:
        return vacio
    t = db.meta_cuenta_dia
    q = sa.select(sa.func.count().label("filas"), sa.func.min(t.c.fecha).label("desde"),
                  sa.func.max(t.c.fecha).label("hasta")).where(t.c.cliente == cliente,
                                                               t.c.ad_account_id.in_(list(cuentas)))
    with db.conectar() as con:
        r = con.execute(q).one()
    return {"filas": int(r.filas or 0), "desde": r.desde, "hasta": r.hasta} if r.filas else vacio


def cuenta_por_dia(cliente, cuentas, desde, hasta):
    """Las filas de meta_cuenta_dia del rango (para el gráfico diario), por fecha y cuenta."""
    if not cuentas:
        return []
    t = db.meta_cuenta_dia
    q = (sa.select(t.c.ad_account_id, t.c.fecha, *[t.c[c] for c in METRICAS_CUENTA])
         .where(*_donde(t, cliente, cuentas, desde, hasta)).order_by(t.c.fecha, t.c.ad_account_id))
    with db.conectar() as con:
        filas = con.execute(q).mappings().all()
    return [dict(ad_account_id=f["ad_account_id"], fecha=f["fecha"], **_medidas(f, METRICAS_CUENTA)) for f in filas]


def totales_por_cuenta(cliente, cuentas, desde, hasta):
    """{ad_account_id: sumas de meta_cuenta_dia en el rango + `dias` (cuántos días hay)}. Solo las cuentas con
    al menos un día en el rango. OJO: `alcance` es la SUMA de los alcances diarios (cota superior, la misma
    persona cuenta cada día); el alcance de verdad de un período es `alcance()`."""
    if not cuentas:
        return {}
    t = db.meta_cuenta_dia
    q = (sa.select(t.c.ad_account_id, sa.func.count().label("dias"), *_sumas(t, METRICAS_CUENTA))
         .where(*_donde(t, cliente, cuentas, desde, hasta)).group_by(t.c.ad_account_id))
    with db.conectar() as con:
        filas = con.execute(q).mappings().all()
    return {f["ad_account_id"]: dict(_medidas(f, METRICAS_CUENTA), dias=int(f["dias"])) for f in filas}


def totales_por_campana(cliente, cuentas, desde, hasta):
    """Una fila por campaña con las sumas de sus anuncios en el rango, más su nombre, estado, objetivo y
    presupuestos (meta_objeto, LEFT JOIN: sin objeto quedan en None). Orden: gasto descendente."""
    if not cuentas:
        return []
    a, c = db.meta_anuncio_dia, db.meta_objeto.alias("c")
    gasto = sa.func.sum(a.c.gasto)
    cols_obj = [c.c.nombre, c.c.estado, c.c.objetivo, c.c.presupuesto_diario, c.c.presupuesto_total]
    q = (sa.select(a.c.ad_account_id, a.c.campaign_id, *cols_obj, *_sumas(a, METRICAS))
         .select_from(a.outerjoin(c, sa.and_(c.c.cliente == a.c.cliente, c.c.objeto_id == a.c.campaign_id)))
         .where(*_donde(a, cliente, cuentas, desde, hasta))
         .group_by(a.c.ad_account_id, a.c.campaign_id, *cols_obj)
         .order_by(gasto.desc(), a.c.campaign_id))
    with db.conectar() as con:
        filas = con.execute(q).mappings().all()
    return [_con_alias_evaluacion(dict(
        ad_account_id=f["ad_account_id"], campaign_id=f["campaign_id"], nombre=f["nombre"], estado=f["estado"],
        objetivo=f["objetivo"], presupuesto_diario=f["presupuesto_diario"],
        presupuesto_total=f["presupuesto_total"], **_medidas(f, METRICAS))) for f in filas]


def totales_por_conjunto(cliente, cuentas, desde, hasta, limite=24, offset=0):
    """Una fila por conjunto con las sumas de sus anuncios en el rango, su nombre, estado, aprendizaje,
    presupuestos y optimización (meta_objeto) y el nombre de su campaña (`campana`). Orden: gasto descendente;
    `limite`/`offset` paginan («Ver más»); `limite=None` trae todos."""
    if not cuentas:
        return []
    a, s, c = db.meta_anuncio_dia, db.meta_objeto.alias("s"), db.meta_objeto.alias("c")
    gasto = sa.func.sum(a.c.gasto)
    cols_obj = [s.c.nombre, s.c.estado, s.c.aprendizaje, s.c.presupuesto_diario, s.c.presupuesto_total,
                s.c.optimizacion, s.c.estrategia_puja, c.c.nombre.label("campana")]
    q = (sa.select(a.c.ad_account_id, a.c.adset_id, a.c.campaign_id, *cols_obj, *_sumas(a, METRICAS))
         .select_from(a.outerjoin(s, sa.and_(s.c.cliente == a.c.cliente, s.c.objeto_id == a.c.adset_id))
                      .outerjoin(c, sa.and_(c.c.cliente == a.c.cliente, c.c.objeto_id == a.c.campaign_id)))
         .where(*_donde(a, cliente, cuentas, desde, hasta))
         .group_by(a.c.ad_account_id, a.c.adset_id, a.c.campaign_id, s.c.nombre, s.c.estado, s.c.aprendizaje,
                   s.c.presupuesto_diario, s.c.presupuesto_total, s.c.optimizacion, s.c.estrategia_puja,
                   c.c.nombre)
         .order_by(gasto.desc(), a.c.adset_id))
    if limite is not None:
        q = q.limit(limite).offset(offset or 0)
    with db.conectar() as con:
        filas = con.execute(q).mappings().all()
    return [_con_alias_evaluacion(dict(
        ad_account_id=f["ad_account_id"], adset_id=f["adset_id"], campaign_id=f["campaign_id"], nombre=f["nombre"],
        campana=f["campana"], estado=f["estado"], aprendizaje=f["aprendizaje"],
        presupuesto_diario=f["presupuesto_diario"], presupuesto_total=f["presupuesto_total"],
        optimizacion=f["optimizacion"], estrategia_puja=f["estrategia_puja"], **_medidas(f, METRICAS)))
        for f in filas]


def totales_por_anuncio(cliente, cuentas, desde, hasta):
    """Una fila por anuncio con las sumas del rango en las claves que espera
    `triple_whale.evaluacion.metricas` (`pedidos` = compras, `ingresos` = valor), su nombre, estado y miniatura
    (meta_objeto), los nombres de su conjunto y campaña, las fechas del primer y último día con datos y los
    días con gasto. `canal` siempre «meta». Orden: gasto descendente."""
    if not cuentas:
        return []
    a, o, s, c = db.meta_anuncio_dia, db.meta_objeto.alias("o"), db.meta_objeto.alias("s"), db.meta_objeto.alias("c")
    gasto = sa.func.sum(a.c.gasto)
    cols_obj = [o.c.nombre.label("anuncio"), o.c.estado, o.c.miniatura_url, s.c.nombre.label("conjunto"),
                c.c.nombre.label("campana")]
    q = (sa.select(a.c.ad_account_id, a.c.ad_id, a.c.adset_id, a.c.campaign_id, *cols_obj,
                   sa.func.min(a.c.fecha).label("primera_fecha"), sa.func.max(a.c.fecha).label("ultima_fecha"),
                   sa.func.sum(sa.case((a.c.gasto > 0, 1), else_=0)).label("dias_con_gasto"),
                   *_sumas(a, METRICAS_ANUNCIO))
         .select_from(a.outerjoin(o, sa.and_(o.c.cliente == a.c.cliente, o.c.objeto_id == a.c.ad_id))
                      .outerjoin(s, sa.and_(s.c.cliente == a.c.cliente, s.c.objeto_id == a.c.adset_id))
                      .outerjoin(c, sa.and_(c.c.cliente == a.c.cliente, c.c.objeto_id == a.c.campaign_id)))
         .where(*_donde(a, cliente, cuentas, desde, hasta))
         .group_by(a.c.ad_account_id, a.c.ad_id, a.c.adset_id, a.c.campaign_id, o.c.nombre, o.c.estado,
                   o.c.miniatura_url, s.c.nombre, c.c.nombre)
         .order_by(gasto.desc(), a.c.ad_id))
    with db.conectar() as con:
        filas = con.execute(q).mappings().all()
    return [_con_alias_evaluacion(dict(
        ad_account_id=f["ad_account_id"], ad_id=f["ad_id"], adset_id=f["adset_id"], campaign_id=f["campaign_id"],
        anuncio=f["anuncio"], conjunto=f["conjunto"], campana=f["campana"], estado=f["estado"],
        miniatura_url=f["miniatura_url"], primera_fecha=f["primera_fecha"], ultima_fecha=f["ultima_fecha"],
        dias_con_gasto=int(f["dias_con_gasto"] or 0), canal="meta", **_medidas(f, METRICAS_ANUNCIO)))
        for f in filas]


def alcance(cliente, cuentas, ventana, nivel="cuenta"):
    """{objeto_id: {"alcance", "frecuencia"}} de esa ventana (7|14|30|90) y nivel (cuenta|campana)."""
    if not cuentas:
        return {}
    t = db.meta_alcance
    q = (sa.select(t.c.objeto_id, t.c.alcance, t.c.frecuencia)
         .where(t.c.cliente == cliente, t.c.ad_account_id.in_(list(cuentas)), t.c.ventana == int(ventana),
                t.c.nivel == nivel))
    with db.conectar() as con:
        filas = con.execute(q).all()
    return {r.objeto_id: {"alcance": int(r.alcance or 0),
                          "frecuencia": None if r.frecuencia is None else float(r.frecuencia)} for r in filas}


def activos(cliente, cuentas):
    """{ad_account_id: {"campana", "conjunto", "anuncio", "aprendizaje_limitado"}}: cuántos objetos están
    ACTIVE (entregando de verdad) y cuántos conjuntos activos tienen aprendizaje limitado (FAIL). Trae una
    entrada por cada cuenta pedida, con ceros si no tiene nada activo."""
    if not cuentas:
        return {}
    t = db.meta_objeto
    q = (sa.select(t.c.ad_account_id, t.c.nivel, sa.func.count().label("n"),
                   sa.func.sum(sa.case((t.c.aprendizaje == "FAIL", 1), else_=0)).label("fail"))
         .where(t.c.cliente == cliente, t.c.ad_account_id.in_(list(cuentas)), t.c.estado == "ACTIVE")
         .group_by(t.c.ad_account_id, t.c.nivel))
    salida = {act: {"campana": 0, "conjunto": 0, "anuncio": 0, "aprendizaje_limitado": 0} for act in cuentas}
    with db.conectar() as con:
        for r in con.execute(q):
            if r.nivel in _NIVELES:
                salida[r.ad_account_id][r.nivel] = int(r.n)
            if r.nivel == "conjunto":
                salida[r.ad_account_id]["aprendizaje_limitado"] = int(r.fail or 0)
    return salida
