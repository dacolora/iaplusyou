"""Único escritor (y lector) de `tw_anuncio_dia`, `tw_tienda_dia`,
`tw_producto_dia`, `tw_evaluacion` (spec 2026-09-28 §3), `tw_creativo` y
`tw_analisis` (tarjetas, spec 2026-10-08 §3). Solo SQLAlchemy Core; nada de
Flask ni de la API de Triple Whale.

Desde 2026-10-08 (spec de varias tiendas §6.1) cada copia es de una tienda
(`tienda_id`): las escrituras reciben la tienda y las lecturas `tienda_id`
como segundo argumento, con `None` = todas las del proyecto (el gasto de un
anuncio que llega por varias tiendas cuenta una vez; los pedidos se suman).

Las dos tablas de métricas son COPIAS: cada sincronización reemplaza un rango
de fechas completo. Triple Whale reatribuye días viejos (un pedido de hoy
puede caer en el clic de hace una semana), así que un día vuelto a pedir
puede tener menos filas que antes: `reemplazar_*` pone en cero (anuncios) o
borra (tienda) el rango ANTES de escribir lo nuevo, en la misma transacción.
"""
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite import insert as insert_sqlite

import db

# Columnas de ads_table y de pixel_joined_tvf en tw_anuncio_dia.
COLUMNAS_DIMENSION = ("cuenta_id", "campana_id", "campana", "conjunto_id", "conjunto", "anuncio", "estado_anuncio",
                      "creative_id", "video_url", "destino_url", "utm_ok")
COLUMNAS_CANAL = ("gasto", "impresiones", "clics", "clics_salida", "compras_canal", "valor_canal", "thruplays",
                  "vistas_3s", "p25", "p50", "p75", "p100")
COLUMNAS_PIXEL = ("pedidos", "ingresos", "nc_pedidos", "nc_ingresos", "sesiones", "carritos", "checkouts")
COLUMNAS_TIENDA = ("gasto", "ingresos", "pedidos", "nc_pedidos", "nc_ingresos", "reembolsos", "cogs", "utilidad_neta")
COLUMNAS_PRODUCTO = ("unidades", "ingresos", "pedidos")
COLUMNAS_POR_TIENDA = ("ingresos", "pedidos", "gasto", "nc_pedidos", "nc_ingresos")   # por_tienda
_LLAVE_ANUNCIO = ["cliente", "tienda_id", "canal", "ad_id", "fecha"]   # uq_tw_anuncio_dia
ESTADOS_EVALUACION = ("en_cola", "analizando", "lista", "error")


def _ceros(columnas):
    return {c: 0 for c in columnas}


# ------------------------------------------------------------ escribir ---
# Cada copia es de UNA tienda (`tienda_id`, spec 2026-10-08 §3.3): poner en
# cero o borrar el rango de una tienda nunca toca las filas de otra. Cada
# `reemplazar_*` comprueba DENTRO de su transacción que la tienda siga siendo del
# proyecto: si la quitaron mientras su sincronización corría no escribe nada, para
# no dejar filas huérfanas que los lectores de «Todas» (filtran solo por cliente)
# contarían.

def _tienda_existe(con, cliente, tienda_id):
    t = db.tw_tienda
    return con.execute(sa.select(t.c.id).where(t.c.id == tienda_id, t.c.cliente == cliente)).first() is not None


def reemplazar_anuncios_canal(cliente, tienda_id, desde, hasta, registros):
    """Lo que reporta cada plataforma para [desde, hasta] según esa tienda.
    Pone en cero las medidas de canal del rango y hace upsert de `registros`
    (dicts con canal, ad_id, fecha, dimensiones y COLUMNAS_CANAL). No toca lo
    del Pixel."""
    t = db.tw_anuncio_dia
    ahora = db.ahora()
    with db.conectar() as con:
        if not _tienda_existe(con, cliente, tienda_id):
            return
        con.execute(t.update().where(t.c.cliente == cliente, t.c.tienda_id == tienda_id,
                                     t.c.fecha >= desde, t.c.fecha <= hasta)
                    .values(**_ceros(COLUMNAS_CANAL)))
        for r in registros:
            valores = {c: r.get(c) for c in COLUMNAS_DIMENSION if r.get(c) is not None}
            valores.update({c: r.get(c) or 0 for c in COLUMNAS_CANAL})
            nuevo = dict(cliente=cliente, tienda_id=tienda_id, fecha=r["fecha"], canal=r["canal"], ad_id=r["ad_id"],
                         actualizado_en=ahora, con_pixel=False, **_ceros(COLUMNAS_PIXEL))
            nuevo.update(valores)
            con.execute(insert_sqlite(t).values(**nuevo).on_conflict_do_update(
                index_elements=_LLAVE_ANUNCIO, set_=dict(valores, actualizado_en=ahora)))


def reemplazar_anuncios_pixel(cliente, tienda_id, desde, hasta, registros):
    """Lo atribuido por el Triple Pixel de esa tienda para [desde, hasta] con
    el modelo y la ventana del proyecto. Mismo patrón: cero en el rango y
    upsert. Todas las filas del rango quedan con `con_pixel=True` («el Pixel
    respondió»): un anuncio sin fila del Pixel no vendió nada según Triple
    Whale, que no es lo mismo que no saberlo (el lanzador usa esa diferencia)."""
    t = db.tw_anuncio_dia
    ahora = db.ahora()
    with db.conectar() as con:
        if not _tienda_existe(con, cliente, tienda_id):
            return
        con.execute(t.update().where(t.c.cliente == cliente, t.c.tienda_id == tienda_id,
                                     t.c.fecha >= desde, t.c.fecha <= hasta)
                    .values(con_pixel=True, **_ceros(COLUMNAS_PIXEL)))
        for r in registros:
            valores = {c: r.get(c) or 0 for c in COLUMNAS_PIXEL}
            valores["con_pixel"] = True
            nuevo = dict(cliente=cliente, tienda_id=tienda_id, fecha=r["fecha"], canal=r["canal"], ad_id=r["ad_id"],
                         actualizado_en=ahora, **_ceros(COLUMNAS_CANAL))
            nuevo.update(valores)
            con.execute(insert_sqlite(t).values(**nuevo).on_conflict_do_update(
                index_elements=_LLAVE_ANUNCIO, set_=dict(valores, actualizado_en=ahora)))


def reemplazar_tienda(cliente, tienda_id, desde, hasta, registros):
    """La tienda por día para [desde, hasta]: borra el rango de ESA tienda y lo vuelve a escribir."""
    t = db.tw_tienda_dia
    ahora = db.ahora()
    with db.conectar() as con:
        if not _tienda_existe(con, cliente, tienda_id):
            return
        con.execute(t.delete().where(t.c.cliente == cliente, t.c.tienda_id == tienda_id,
                                     t.c.fecha >= desde, t.c.fecha <= hasta))
        for r in registros:
            con.execute(t.insert().values(cliente=cliente, tienda_id=tienda_id, fecha=r["fecha"], actualizado_en=ahora,
                                          **{c: r.get(c) or 0 for c in COLUMNAS_TIENDA}))


def reemplazar_productos(cliente, tienda_id, desde, hasta, registros):
    """Ventas por producto y día de esa tienda para [desde, hasta]: borra el
    rango y lo vuelve a escribir (`registros`: fecha, producto_id, nombre,
    sku y COLUMNAS_PRODUCTO)."""
    t = db.tw_producto_dia
    ahora = db.ahora()
    with db.conectar() as con:
        if not _tienda_existe(con, cliente, tienda_id):
            return
        con.execute(t.delete().where(t.c.cliente == cliente, t.c.tienda_id == tienda_id,
                                     t.c.fecha >= desde, t.c.fecha <= hasta))
        for r in registros:
            con.execute(t.insert().values(cliente=cliente, tienda_id=tienda_id, fecha=r["fecha"],
                                          producto_id=r["producto_id"], nombre=r.get("nombre"), sku=r.get("sku"),
                                          actualizado_en=ahora, **{c: r.get(c) or 0 for c in COLUMNAS_PRODUCTO}))


# ------------------------------------------------------------- leer ---
# `tienda_id` entero = esa tienda; None = TODAS las del proyecto (spec §6.1).

def _anuncio_dia(cliente, tienda_id, desde=None, hasta=None, canal=None):
    """Una fila por (canal, ad_id, fecha). Con una tienda, sus filas. Con todas,
    medidas de canal con MAX (el mismo anuncio llega por cada tienda que comparte
    la cuenta: su gasto se cuenta una vez; con cuentas separadas los ad_id no se
    repiten y MAX es el único valor) y del Pixel con SUMA (cada tienda atribuye
    sus propios pedidos)."""
    t = db.tw_anuncio_dia
    cond = [t.c.cliente == cliente]
    if desde:
        cond.append(t.c.fecha >= desde)
    if hasta:
        cond.append(t.c.fecha <= hasta)
    if tienda_id is not None:
        cond.append(t.c.tienda_id == tienda_id)
    if canal:
        cond.append(t.c.canal == canal)
    medidas = ([sa.func.max(getattr(t.c, c)).label(c) for c in COLUMNAS_CANAL]
               + [sa.func.sum(getattr(t.c, c)).label(c) for c in COLUMNAS_PIXEL]
               + [sa.func.max(sa.cast(t.c.con_pixel, sa.Integer)).label("con_pixel")]
               + [sa.func.max(getattr(t.c, c)).label(c) for c in COLUMNAS_DIMENSION if c != "utm_ok"]
               + [sa.func.min(sa.cast(t.c.utm_ok, sa.Integer)).label("utm_ok")])
    return (sa.select(t.c.canal, t.c.ad_id, t.c.fecha, *medidas).where(*cond)
            .group_by(t.c.canal, t.c.ad_id, t.c.fecha).subquery())


def _sumas(t):
    return [sa.func.coalesce(sa.func.sum(getattr(t.c, c)), 0).label(c) for c in COLUMNAS_CANAL + COLUMNAS_PIXEL]


def totales_por_anuncio(cliente, tienda_id, desde, hasta, canal=None):
    """Una fila por (canal, anuncio) con las medidas sumadas en [desde, hasta]
    y las dimensiones más recientes que no estén vacías. Solo anuncios con
    algo que mirar (gasto, impresiones o pedidos)."""
    d = _anuncio_dia(cliente, tienda_id, desde, hasta, canal)
    q = (sa.select(d.c.canal, d.c.ad_id,
                   sa.func.max(d.c.campana).label("campana"), sa.func.max(d.c.campana_id).label("campana_id"),
                   sa.func.max(d.c.conjunto).label("conjunto"), sa.func.max(d.c.anuncio).label("anuncio"),
                   sa.func.max(d.c.cuenta_id).label("cuenta_id"), sa.func.max(d.c.creative_id).label("creative_id"),
                   sa.func.max(d.c.video_url).label("video_url"), sa.func.max(d.c.destino_url).label("destino_url"),
                   sa.func.min(d.c.utm_ok).label("utm_ok"),
                   sa.func.min(d.c.fecha).label("primera_fecha"), sa.func.max(d.c.fecha).label("ultima_fecha"),
                   sa.func.sum(sa.case((d.c.gasto > 0, 1), else_=0)).label("dias_con_gasto"),
                   *_sumas(d))
         .group_by(d.c.canal, d.c.ad_id)
         .having(sa.or_(sa.func.sum(d.c.gasto) > 0, sa.func.sum(d.c.impresiones) > 0, sa.func.sum(d.c.pedidos) > 0)))
    with db.conectar() as con:
        filas = [dict(r._mapping) for r in con.execute(q)]
    for f in filas:
        f["utm_ok"] = None if f["utm_ok"] is None else bool(f["utm_ok"])
    return filas


def totales_anuncio(cliente, tienda_id, canal, ad_id, desde, hasta=None):
    """Las medidas sumadas de UN anuncio en UNA tienda desde `desde` (para el
    snapshot de un experimento, que vende en la tienda de su país). None si
    Triple Whale todavía no trajo ninguna fila suya. Sin `tienda_id` lanza
    `ValueError`: aquí `None` no es «todas» y leer las filas sin tienda daría
    un None que parece «sin datos»."""
    if tienda_id is None:
        raise ValueError("totales_anuncio pide la tienda")
    t = db.tw_anuncio_dia
    cond = [t.c.cliente == cliente, t.c.tienda_id == tienda_id, t.c.canal == canal, t.c.ad_id == str(ad_id),
            t.c.fecha >= desde]
    if hasta:
        cond.append(t.c.fecha <= hasta)
    q = sa.select(sa.func.count().label("n"), sa.func.max(sa.cast(t.c.con_pixel, sa.Integer)).label("con_pixel"),
                  *_sumas(t)).where(*cond)
    with db.conectar() as con:
        fila = dict(con.execute(q).one()._mapping)
    if not fila["n"]:
        return None
    fila["con_pixel"] = bool(fila["con_pixel"])
    return fila


def serie_anuncios(cliente, tienda_id, desde, hasta):
    """Por día: gasto de anuncios e ingresos atribuidos por el Pixel."""
    d = _anuncio_dia(cliente, tienda_id, desde, hasta)
    q = (sa.select(d.c.fecha, sa.func.coalesce(sa.func.sum(d.c.gasto), 0).label("gasto"),
                   sa.func.coalesce(sa.func.sum(d.c.ingresos), 0).label("ingresos"),
                   sa.func.coalesce(sa.func.sum(d.c.pedidos), 0).label("pedidos"))
         .group_by(d.c.fecha).order_by(d.c.fecha))
    with db.conectar() as con:
        return [dict(r._mapping) for r in con.execute(q)]


def _duplicado_por_dia(cliente, desde, hasta):
    """Subconsulta (fecha, duplicado): por día, Σ por anuncio de (suma − máximo)
    de su gasto entre las tiendas. Es lo que «Todas» contaría de más si sumara
    el gasto de cada tienda con una cuenta publicitaria compartida."""
    t = db.tw_anuncio_dia
    por_anuncio = (sa.select(t.c.fecha, (sa.func.sum(t.c.gasto) - sa.func.max(t.c.gasto)).label("duplicado"))
                   .where(t.c.cliente == cliente, t.c.fecha >= desde, t.c.fecha <= hasta)
                   .group_by(t.c.canal, t.c.ad_id, t.c.fecha).subquery())
    return (sa.select(por_anuncio.c.fecha, sa.func.sum(por_anuncio.c.duplicado).label("duplicado"))
            .group_by(por_anuncio.c.fecha).subquery())


def gasto_duplicado(cliente, desde, hasta, tienda_id=None):
    """Gasto de anuncios que llega repetido por varias tiendas en [desde, hasta]
    (mayor que 0 = hay tiendas que comparten cuenta publicitaria). Sin tienda
    («Todas»): Σ por (canal, anuncio, día) de suma − máximo, lo que «Todas»
    contaría de más. Con tienda: el gasto de ESA tienda en los (canal, anuncio,
    día) que también traen gasto por otra tienda del proyecto; una tienda con
    cuenta propia da 0 aunque otras dos compartan (revisión del guardián del
    gasto, 2026-10-08). Una sola consulta, siempre filtrada por cliente."""
    if tienda_id is None:
        d = _duplicado_por_dia(cliente, desde, hasta)
        q = sa.select(sa.func.coalesce(sa.func.sum(d.c.duplicado), 0))
    else:
        t, o = db.tw_anuncio_dia, db.tw_anuncio_dia.alias("otra")
        en_otra = (sa.select(o.c.id).where(o.c.cliente == cliente, o.c.tienda_id != tienda_id,
                                           o.c.canal == t.c.canal, o.c.ad_id == t.c.ad_id,
                                           o.c.fecha == t.c.fecha, o.c.gasto > 0)
                   .exists())
        q = sa.select(sa.func.coalesce(sa.func.sum(t.c.gasto), 0)).where(
            t.c.cliente == cliente, t.c.tienda_id == tienda_id, t.c.fecha >= desde, t.c.fecha <= hasta, en_otra)
    with db.conectar() as con:
        return float(con.execute(q).scalar() or 0)


def serie_tienda(cliente, tienda_id, desde, hasta):
    """La tienda por día. Con todas, suma las tiendas y le quita al `gasto` el
    gasto duplicado de ese día (se lo devuelve a `utilidad_neta`, que lo había
    restado de más): el gasto compartido cuenta una vez y el que no viene de
    anuncios queda intacto."""
    t = db.tw_tienda_dia
    cond = [t.c.cliente == cliente, t.c.fecha >= desde, t.c.fecha <= hasta]
    if tienda_id is not None:
        q = sa.select(t.c.fecha, *[getattr(t.c, c) for c in COLUMNAS_TIENDA]).where(
            *cond, t.c.tienda_id == tienda_id).order_by(t.c.fecha)
    else:
        s = (sa.select(t.c.fecha, *[sa.func.sum(getattr(t.c, c)).label(c) for c in COLUMNAS_TIENDA])
             .where(*cond).group_by(t.c.fecha).subquery())
        d = _duplicado_por_dia(cliente, desde, hasta)
        dup = sa.func.coalesce(d.c.duplicado, 0)
        columnas = [(s.c[c] - dup).label(c) if c == "gasto" else (s.c[c] + dup).label(c) if c == "utilidad_neta"
                    else s.c[c] for c in COLUMNAS_TIENDA]
        q = (sa.select(s.c.fecha, *columnas).select_from(s.outerjoin(d, d.c.fecha == s.c.fecha))
             .order_by(s.c.fecha))
    with db.conectar() as con:
        return [dict(r._mapping) for r in con.execute(q)]


def por_tienda(cliente, desde, hasta, desde_prev, hasta_prev):
    """Una fila por tienda del proyecto (también las que no tienen cifras), por
    id: {"tienda_id", "actual", "previo"}, cada periodo con COLUMNAS_POR_TIENDA
    sumadas como `serie_tienda` de esa tienda. Una sola consulta."""
    ti, t = db.tw_tienda, db.tw_tienda_dia
    en_actual = sa.and_(t.c.fecha >= desde, t.c.fecha <= hasta)
    en_previo = sa.and_(t.c.fecha >= desde_prev, t.c.fecha <= hasta_prev)

    def _suma(periodo, c, etiqueta):
        return sa.func.coalesce(sa.func.sum(sa.case((periodo, getattr(t.c, c)), else_=0)), 0).label(etiqueta)

    q = (sa.select(ti.c.id, *[_suma(en_actual, c, f"a_{c}") for c in COLUMNAS_POR_TIENDA],
                   *[_suma(en_previo, c, f"p_{c}") for c in COLUMNAS_POR_TIENDA])
         .select_from(ti.outerjoin(t, sa.and_(t.c.cliente == ti.c.cliente, t.c.tienda_id == ti.c.id,
                                              sa.or_(en_actual, en_previo))))
         .where(ti.c.cliente == cliente).group_by(ti.c.id).order_by(ti.c.id))
    with db.conectar() as con:
        filas = [r._mapping for r in con.execute(q)]
    return [{"tienda_id": f["id"],
             "actual": {c: f[f"a_{c}"] for c in COLUMNAS_POR_TIENDA},
             "previo": {c: f[f"p_{c}"] for c in COLUMNAS_POR_TIENDA}} for f in filas]


def top_productos(cliente, tienda_id, desde, hasta, limite=10):
    """Los productos que más vendieron en [desde, hasta] (por ingresos), con
    el nombre y el sku más recientes que no estén vacíos. Con una tienda, por
    `producto_id`. Con todas, por nombre normalizado (minúsculas, sin espacios
    de más): cada tienda de Shopify tiene su propio id para el mismo producto;
    `producto_id` es el menor del grupo."""
    t = db.tw_producto_dia
    cond = [t.c.cliente == cliente, t.c.fecha >= desde, t.c.fecha <= hasta]
    if tienda_id is not None:
        cond.append(t.c.tienda_id == tienda_id)
        grupo, pid = t.c.producto_id, t.c.producto_id
    else:
        nombre = sa.func.lower(sa.func.trim(t.c.nombre))
        for _ in range(3):   # colapsa hasta 8 espacios seguidos (SQLite no tiene regexp_replace)
            nombre = sa.func.replace(nombre, "  ", " ")
        grupo = sa.func.coalesce(sa.func.nullif(nombre, ""), sa.literal("id:") + t.c.producto_id)
        pid = sa.func.min(t.c.producto_id).label("producto_id")
    q = (sa.select(pid, sa.func.max(t.c.nombre).label("nombre"), sa.func.max(t.c.sku).label("sku"),
                   sa.func.coalesce(sa.func.sum(t.c.unidades), 0).label("unidades"),
                   sa.func.coalesce(sa.func.sum(t.c.ingresos), 0).label("ingresos"),
                   sa.func.coalesce(sa.func.sum(t.c.pedidos), 0).label("pedidos"))
         .where(*cond).group_by(grupo).order_by(sa.desc("ingresos"), sa.desc("unidades")).limit(limite))
    with db.conectar() as con:
        return [dict(r._mapping) for r in con.execute(q)]


def _hay(tabla, cliente, tienda_id):
    cond = [tabla.c.cliente == cliente]
    if tienda_id is not None:
        cond.append(tabla.c.tienda_id == tienda_id)
    with db.conectar() as con:
        return bool(con.execute(sa.select(tabla.c.id).where(*cond).limit(1)).first())


def hay_productos(cliente, tienda_id=None):
    return _hay(db.tw_producto_dia, cliente, tienda_id)


def hay_tienda(cliente, tienda_id=None):
    return _hay(db.tw_tienda_dia, cliente, tienda_id)


def rango(cliente, tienda_id=None):
    """{"desde", "hasta", "filas", "anuncios"} de lo copiado; ceros si nada.
    `filas` cuenta (canal, anuncio, día), una vez aunque llegue por varias tiendas."""
    d = _anuncio_dia(cliente, tienda_id)
    q = sa.select(sa.func.min(d.c.fecha), sa.func.max(d.c.fecha), sa.func.count(),
                  sa.func.count(sa.distinct(d.c.ad_id)))
    with db.conectar() as con:
        desde, hasta, filas, anuncios = con.execute(q).one()
    return {"desde": desde, "hasta": hasta, "filas": int(filas or 0), "anuncios": int(anuncios or 0)}


def canales(cliente, tienda_id, desde, hasta):
    """Canales con gasto o impresiones en el rango, del que más gastó al que menos."""
    d = _anuncio_dia(cliente, tienda_id, desde, hasta)
    q = (sa.select(d.c.canal).group_by(d.c.canal)
         .having(sa.or_(sa.func.sum(d.c.gasto) > 0, sa.func.sum(d.c.impresiones) > 0))
         .order_by(sa.func.sum(d.c.gasto).desc()))
    with db.conectar() as con:
        return [r[0] for r in con.execute(q)]


# ------------------------------------------------------- evaluaciones ---

def crear_evaluacion(cliente, desde, hasta, moneda, anuncios, pedido_por=None):
    ahora = db.ahora()
    t = db.tw_evaluacion
    with db.conectar() as con:
        return con.execute(t.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, estado="en_cola", desde=desde, hasta=hasta,
            moneda=moneda, anuncios=list(anuncios or []), resultado={}, usd=0.0, pedido_por=pedido_por, extra={},
        )).inserted_primary_key[0]


def actualizar_evaluacion(evaluacion_id, **campos):
    if "estado" in campos and campos["estado"] not in ESTADOS_EVALUACION:
        raise ValueError(f"estado inválido: {campos['estado']}")
    t = db.tw_evaluacion
    with db.conectar() as con:
        return con.execute(t.update().where(t.c.id == evaluacion_id)
                           .values(actualizado_en=db.ahora(), **campos)).rowcount == 1


def evaluacion(cliente, evaluacion_id):
    t = db.tw_evaluacion
    with db.conectar() as con:
        fila = con.execute(sa.select(t).where(t.c.id == evaluacion_id, t.c.cliente == cliente)).first()
    return dict(fila._mapping) if fila else None


def evaluaciones(cliente, limite=5):
    t = db.tw_evaluacion
    with db.conectar() as con:
        return [dict(r._mapping) for r in con.execute(
            sa.select(t).where(t.c.cliente == cliente).order_by(t.c.id.desc()).limit(limite))]


def borrar_evaluacion(cliente, evaluacion_id):
    t = db.tw_evaluacion
    with db.conectar() as con:
        return con.execute(t.delete().where(t.c.id == evaluacion_id, t.c.cliente == cliente)).rowcount == 1


def piezas_creatv(cliente, ad_ids):
    """{meta_ad_id: {"ep_id", "experimento_id", "experimento", "estado",
    "pieza_id", "tipo", "url_video", "url_miniatura", "tw_idea"}} de los
    anuncios que lanzó Creatv (experimento_pieza + su pieza): para marcarlos
    en la evaluación, pausarlos/activarlos desde la pestaña y mandar a Claude
    los fotogramas del video real (que vive en R2) en vez de la miniatura.
    `tw_idea` es `{"evaluacion_id", "idea", "titulo"}` cuando la pieza nació
    de una idea de la evaluación con IA («Llevar a Crear»), si no None."""
    ids = [str(a) for a in ad_ids if a]
    if not ids:
        return {}
    ep, ex, pz, cp = db.experimento_pieza, db.experimento, db.pieza, db.concepto
    q = (sa.select(ep.c.meta_ad_id, ep.c.id, ep.c.experimento_id, ex.c.nombre, ep.c.estado, ep.c.pieza_id,
                   pz.c.tipo, pz.c.url_video, pz.c.url_miniatura, cp.c.extra)
         .select_from(ep.join(ex, ex.c.id == ep.c.experimento_id).outerjoin(pz, pz.c.id == ep.c.pieza_id)
                      .outerjoin(cp, cp.c.id == pz.c.concepto_id))
         .where(ex.c.cliente == cliente, ep.c.meta_ad_id.in_(ids)))
    with db.conectar() as con:
        return {r[0]: {"ep_id": r[1], "experimento_id": r[2], "experimento": r[3], "estado": r[4],
                       "pieza_id": r[5], "tipo": "imagen" if r[6] == "imagen" else "video",
                       "url_video": r[7], "url_miniatura": r[8], "tw_idea": _tw_idea(r[9])} for r in con.execute(q)}


def _tw_idea(extra_concepto):
    v = (extra_concepto or {}).get("tw_idea") if isinstance(extra_concepto, dict) else None
    return dict(v) if isinstance(v, dict) and v.get("evaluacion_id") is not None else None


def piezas_de_evaluacion(cliente, evaluacion_id):
    """{índice de la idea: [{"cf_id", "pieza_id", "titulo", "estado", "tipo",
    "url_video", "creado_en"}, …]} — las piezas de Crear que nacieron de cada
    idea de esa evaluación (`concepto.extra.tw_idea`), de la más vieja a la
    más nueva. `estado` es el de Crear (`prompt_pendiente | prompt_listo |
    video_generando | video_listo | error`)."""
    import creative_flow  # el mismo mapa pieza.estado → estado de Crear que usa `creative_flow.cargar`
    cp, pz = db.concepto, db.pieza
    q = (sa.select(cp.c.legado_id, pz.c.id, cp.c.extra, pz.c.estado, pz.c.tipo, pz.c.url_video, pz.c.creado_en)
         .select_from(cp.join(pz, pz.c.concepto_id == cp.c.id))
         .where(cp.c.cliente == cliente, cp.c.legado_id.isnot(None), pz.c.tipo != "final",
                sa.func.json_extract(cp.c.extra, "$.tw_idea.evaluacion_id") == int(evaluacion_id))
         .order_by(pz.c.id))
    salida = {}
    with db.conectar() as con:
        for cf_id, pid, extra, estado, tipo, url_video, creado_en in con.execute(q):
            extra = extra or {}
            origen = extra.get("tw_idea") or {}
            try:
                indice = int(origen.get("idea"))
            except (TypeError, ValueError):
                continue
            estado_crear = extra.get("estado_legado") or creative_flow._PIEZA_A_ESTADO.get(estado, estado)
            titulo = " ".join(str(extra.get("accion_central") or "").split())[:80] or cf_id
            salida.setdefault(indice, []).append({
                "cf_id": cf_id, "pieza_id": pid, "titulo": titulo, "estado": estado_crear,
                "tipo": "imagen" if (extra.get("tipo") or tipo) == "imagen" else "video",
                "url_video": url_video, "creado_en": creado_en})
    return salida



# ------------------------------------------------ creativos (spec tarjetas §3.1) ---
COLUMNAS_CREATIVO = ("tipo", "imagen_url", "video_url", "titulo", "copy", "cta", "duracion_s")


def reemplazar_creativos(cliente, tienda_id, registros):
    """Upsert del anuncio tal cual (`registros`: canal, ad_id y COLUMNAS_CREATIVO). Sin tienda: el mismo anuncio
    llega igual por todas. Un valor vacío no pisa uno guardado (la consulta mínima o un tramo sin él). Como los
    demás `reemplazar_*`, no escribe si la tienda ya no es del proyecto."""
    t = db.tw_creativo
    ahora = db.ahora()
    with db.conectar() as con:
        if not _tienda_existe(con, cliente, tienda_id):
            return
        for r in registros:
            valores = {c: r.get(c) for c in COLUMNAS_CREATIVO if r.get(c) not in (None, "")}
            con.execute(insert_sqlite(t).values(cliente=cliente, canal=r["canal"], ad_id=r["ad_id"],
                                                actualizado_en=ahora, **valores)
                        .on_conflict_do_update(index_elements=["cliente", "canal", "ad_id"],
                                               set_=dict(valores, actualizado_en=ahora)))


def _por_claves(tabla, cliente, claves):
    """Condición `(canal, ad_id) IN claves` sobre `tabla` del cliente (una consulta para toda una página)."""
    pares = sorted({(str(c), str(a)) for c, a in claves})
    return sa.and_(tabla.c.cliente == cliente,
                   sa.or_(*[sa.and_(tabla.c.canal == c, tabla.c.ad_id == a) for c, a in pares]))


def creativos(cliente, claves):
    """{(canal, ad_id): {COLUMNAS_CREATIVO}} de esos anuncios, en una consulta."""
    if not claves:
        return {}
    t = db.tw_creativo
    with db.conectar() as con:
        filas = con.execute(sa.select(t).where(_por_claves(t, cliente, claves))).all()
    return {(f.canal, f.ad_id): {c: getattr(f, c) for c in COLUMNAS_CREATIVO} for f in filas}


# ------------------------------------------------- análisis (spec tarjetas §3.2) ---

def crear_analisis(cliente, tienda_id, canal, ad_id, desde, hasta, moneda, foto, pedido_por=None):
    ahora = db.ahora()
    t = db.tw_analisis
    with db.conectar() as con:
        return con.execute(t.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, tienda_id=tienda_id, canal=canal, ad_id=str(ad_id),
            estado="en_cola", desde=desde, hasta=hasta, moneda=moneda, foto=dict(foto or {}), resultado={}, medios={},
            usd=0.0, pedido_por=pedido_por)).inserted_primary_key[0]


def actualizar_analisis(analisis_id, **campos):
    if "estado" in campos and campos["estado"] not in ESTADOS_EVALUACION:
        raise ValueError(f"estado inválido: {campos['estado']}")
    t = db.tw_analisis
    with db.conectar() as con:
        return con.execute(t.update().where(t.c.id == analisis_id)
                           .values(actualizado_en=db.ahora(), **campos)).rowcount == 1


def analisis_anuncio(cliente, analisis_id):
    t = db.tw_analisis
    with db.conectar() as con:
        fila = con.execute(sa.select(t).where(t.c.id == analisis_id, t.c.cliente == cliente)).first()
    return dict(fila._mapping) if fila else None


def ultimos_analisis(cliente, claves):
    """{(canal, ad_id): fila} con el análisis más nuevo de cada anuncio, en UNA consulta."""
    if not claves:
        return {}
    t = db.tw_analisis
    ultimo = (sa.select(sa.func.max(t.c.id)).where(_por_claves(t, cliente, claves))
              .group_by(t.c.canal, t.c.ad_id))
    with db.conectar() as con:
        filas = con.execute(sa.select(t).where(t.c.id.in_(ultimo))).all()
    return {(f.canal, f.ad_id): dict(f._mapping) for f in filas}


def analisis_en_curso(cliente, canal, ad_id):
    t = db.tw_analisis
    with db.conectar() as con:
        return con.execute(sa.select(t.c.id).where(
            t.c.cliente == cliente, t.c.canal == canal, t.c.ad_id == str(ad_id),
            t.c.estado.in_(("en_cola", "analizando"))).limit(1)).first() is not None


def borrar_analisis(cliente, analisis_id):
    t = db.tw_analisis
    with db.conectar() as con:
        return con.execute(t.delete().where(t.c.id == analisis_id, t.c.cliente == cliente)).rowcount == 1


def piezas_de_analisis(cliente, analisis_ids):
    """{analisis_id: [{"cf_id", "pieza_id", "titulo", "estado"}]} — piezas de Crear que nacieron de la versión
    mejorada de cada análisis (`concepto.extra.tw_idea.analisis_id`), en una consulta."""
    ids = sorted({int(a) for a in analisis_ids or []})
    if not ids:
        return {}
    import creative_flow
    cp, pz = db.concepto, db.pieza
    aid = sa.func.json_extract(cp.c.extra, "$.tw_idea.analisis_id")
    q = (sa.select(aid.label("aid"), cp.c.legado_id, pz.c.id, cp.c.extra, pz.c.estado)
         .select_from(cp.join(pz, pz.c.concepto_id == cp.c.id))
         .where(cp.c.cliente == cliente, cp.c.legado_id.isnot(None), pz.c.tipo != "final", aid.in_(ids))
         .order_by(pz.c.id))
    salida = {}
    with db.conectar() as con:
        for a, cf_id, pid, extra, estado in con.execute(q):
            extra = extra or {}
            titulo = " ".join(str(extra.get("accion_central") or "").split())[:80] or cf_id
            salida.setdefault(int(a), []).append({
                "cf_id": cf_id, "pieza_id": pid, "titulo": titulo,
                "estado": extra.get("estado_legado") or creative_flow._PIEZA_A_ESTADO.get(estado, estado)})
    return salida
