"""Único escritor (y lector) de `tw_anuncio_dia`, `tw_tienda_dia` y
`tw_evaluacion` (spec 2026-09-28 §3). Solo SQLAlchemy Core; nada de Flask ni
de la API de Triple Whale.

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
ESTADOS_EVALUACION = ("en_cola", "analizando", "lista", "error")


def _ceros(columnas):
    return {c: 0 for c in columnas}


# ------------------------------------------------------------ escribir ---

def reemplazar_anuncios_canal(cliente, desde, hasta, registros):
    """Lo que reporta cada plataforma para [desde, hasta]. Pone en cero las
    medidas de canal del rango y hace upsert de `registros` (dicts con canal,
    ad_id, fecha, dimensiones y COLUMNAS_CANAL). No toca lo del Pixel."""
    t = db.tw_anuncio_dia
    ahora = db.ahora()
    with db.conectar() as con:
        con.execute(t.update().where(t.c.cliente == cliente, t.c.fecha >= desde, t.c.fecha <= hasta)
                    .values(**_ceros(COLUMNAS_CANAL)))
        for r in registros:
            valores = {c: r.get(c) for c in COLUMNAS_DIMENSION if r.get(c) is not None}
            valores.update({c: r.get(c) or 0 for c in COLUMNAS_CANAL})
            nuevo = dict(cliente=cliente, fecha=r["fecha"], canal=r["canal"], ad_id=r["ad_id"],
                         actualizado_en=ahora, con_pixel=False, **_ceros(COLUMNAS_PIXEL))
            nuevo.update(valores)
            con.execute(insert_sqlite(t).values(**nuevo).on_conflict_do_update(
                index_elements=["cliente", "canal", "ad_id", "fecha"], set_=dict(valores, actualizado_en=ahora)))


def reemplazar_anuncios_pixel(cliente, desde, hasta, registros):
    """Lo atribuido por el Triple Pixel para [desde, hasta] con el modelo y la
    ventana del proyecto. Mismo patrón: cero en el rango y upsert. Todas las
    filas del rango quedan con `con_pixel=True` («el Pixel respondió»): un
    anuncio sin fila del Pixel no vendió nada según Triple Whale, que no es
    lo mismo que no saberlo (el lanzador usa esa diferencia)."""
    t = db.tw_anuncio_dia
    ahora = db.ahora()
    with db.conectar() as con:
        con.execute(t.update().where(t.c.cliente == cliente, t.c.fecha >= desde, t.c.fecha <= hasta)
                    .values(con_pixel=True, **_ceros(COLUMNAS_PIXEL)))
        for r in registros:
            valores = {c: r.get(c) or 0 for c in COLUMNAS_PIXEL}
            valores["con_pixel"] = True
            nuevo = dict(cliente=cliente, fecha=r["fecha"], canal=r["canal"], ad_id=r["ad_id"],
                         actualizado_en=ahora, **_ceros(COLUMNAS_CANAL))
            nuevo.update(valores)
            con.execute(insert_sqlite(t).values(**nuevo).on_conflict_do_update(
                index_elements=["cliente", "canal", "ad_id", "fecha"], set_=dict(valores, actualizado_en=ahora)))


def reemplazar_tienda(cliente, desde, hasta, registros):
    """La tienda por día para [desde, hasta]: borra el rango y lo vuelve a escribir."""
    t = db.tw_tienda_dia
    ahora = db.ahora()
    with db.conectar() as con:
        con.execute(t.delete().where(t.c.cliente == cliente, t.c.fecha >= desde, t.c.fecha <= hasta))
        for r in registros:
            con.execute(t.insert().values(cliente=cliente, fecha=r["fecha"], actualizado_en=ahora,
                                          **{c: r.get(c) or 0 for c in COLUMNAS_TIENDA}))


def reemplazar_productos(cliente, desde, hasta, registros):
    """Ventas por producto y día para [desde, hasta]: borra el rango y lo
    vuelve a escribir (`registros`: fecha, producto_id, nombre, sku y
    COLUMNAS_PRODUCTO)."""
    t = db.tw_producto_dia
    ahora = db.ahora()
    with db.conectar() as con:
        con.execute(t.delete().where(t.c.cliente == cliente, t.c.fecha >= desde, t.c.fecha <= hasta))
        for r in registros:
            con.execute(t.insert().values(cliente=cliente, fecha=r["fecha"], producto_id=r["producto_id"],
                                          nombre=r.get("nombre"), sku=r.get("sku"), actualizado_en=ahora,
                                          **{c: r.get(c) or 0 for c in COLUMNAS_PRODUCTO}))


# ------------------------------------------------------------- leer ---

def _sumas(t):
    return [sa.func.coalesce(sa.func.sum(getattr(t.c, c)), 0).label(c) for c in COLUMNAS_CANAL + COLUMNAS_PIXEL]


def totales_por_anuncio(cliente, desde, hasta, canal=None):
    """Una fila por (canal, anuncio) con las medidas sumadas en [desde, hasta]
    y las dimensiones más recientes que no estén vacías. Solo anuncios con
    algo que mirar (gasto, impresiones o pedidos)."""
    t = db.tw_anuncio_dia
    cond = [t.c.cliente == cliente, t.c.fecha >= desde, t.c.fecha <= hasta]
    if canal:
        cond.append(t.c.canal == canal)
    q = (sa.select(t.c.canal, t.c.ad_id,
                   sa.func.max(t.c.campana).label("campana"), sa.func.max(t.c.campana_id).label("campana_id"),
                   sa.func.max(t.c.conjunto).label("conjunto"), sa.func.max(t.c.anuncio).label("anuncio"),
                   sa.func.max(t.c.cuenta_id).label("cuenta_id"), sa.func.max(t.c.creative_id).label("creative_id"),
                   sa.func.max(t.c.video_url).label("video_url"), sa.func.max(t.c.destino_url).label("destino_url"),
                   sa.func.min(sa.cast(t.c.utm_ok, sa.Integer)).label("utm_ok"),
                   sa.func.min(t.c.fecha).label("primera_fecha"), sa.func.max(t.c.fecha).label("ultima_fecha"),
                   sa.func.sum(sa.case((t.c.gasto > 0, 1), else_=0)).label("dias_con_gasto"),
                   *_sumas(t))
         .where(*cond).group_by(t.c.canal, t.c.ad_id)
         .having(sa.or_(sa.func.sum(t.c.gasto) > 0, sa.func.sum(t.c.impresiones) > 0, sa.func.sum(t.c.pedidos) > 0)))
    with db.conectar() as con:
        filas = [dict(r._mapping) for r in con.execute(q)]
    for f in filas:
        f["utm_ok"] = None if f["utm_ok"] is None else bool(f["utm_ok"])
    return filas


def totales_anuncio(cliente, canal, ad_id, desde, hasta=None):
    """Las medidas sumadas de UN anuncio desde `desde` (para el snapshot de un
    experimento). None si Triple Whale todavía no trajo ninguna fila suya."""
    t = db.tw_anuncio_dia
    cond = [t.c.cliente == cliente, t.c.canal == canal, t.c.ad_id == str(ad_id), t.c.fecha >= desde]
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


def serie_anuncios(cliente, desde, hasta):
    """Por día: gasto de anuncios e ingresos atribuidos por el Pixel."""
    t = db.tw_anuncio_dia
    q = (sa.select(t.c.fecha, sa.func.coalesce(sa.func.sum(t.c.gasto), 0).label("gasto"),
                   sa.func.coalesce(sa.func.sum(t.c.ingresos), 0).label("ingresos"),
                   sa.func.coalesce(sa.func.sum(t.c.pedidos), 0).label("pedidos"))
         .where(t.c.cliente == cliente, t.c.fecha >= desde, t.c.fecha <= hasta)
         .group_by(t.c.fecha).order_by(t.c.fecha))
    with db.conectar() as con:
        return [dict(r._mapping) for r in con.execute(q)]


def serie_tienda(cliente, desde, hasta):
    t = db.tw_tienda_dia
    q = (sa.select(t.c.fecha, *[getattr(t.c, c) for c in COLUMNAS_TIENDA])
         .where(t.c.cliente == cliente, t.c.fecha >= desde, t.c.fecha <= hasta).order_by(t.c.fecha))
    with db.conectar() as con:
        return [dict(r._mapping) for r in con.execute(q)]


def top_productos(cliente, desde, hasta, limite=10):
    """Los productos que más vendieron en [desde, hasta] (por ingresos), con
    el nombre y el sku más recientes que no estén vacíos."""
    t = db.tw_producto_dia
    q = (sa.select(t.c.producto_id, sa.func.max(t.c.nombre).label("nombre"), sa.func.max(t.c.sku).label("sku"),
                   sa.func.coalesce(sa.func.sum(t.c.unidades), 0).label("unidades"),
                   sa.func.coalesce(sa.func.sum(t.c.ingresos), 0).label("ingresos"),
                   sa.func.coalesce(sa.func.sum(t.c.pedidos), 0).label("pedidos"))
         .where(t.c.cliente == cliente, t.c.fecha >= desde, t.c.fecha <= hasta)
         .group_by(t.c.producto_id).order_by(sa.desc("ingresos"), sa.desc("unidades")).limit(limite))
    with db.conectar() as con:
        return [dict(r._mapping) for r in con.execute(q)]


def hay_productos(cliente):
    t = db.tw_producto_dia
    with db.conectar() as con:
        return bool(con.execute(sa.select(t.c.id).where(t.c.cliente == cliente).limit(1)).first())


def rango(cliente):
    """{"desde", "hasta", "filas", "anuncios"} de lo copiado; ceros si nada."""
    t = db.tw_anuncio_dia
    q = sa.select(sa.func.min(t.c.fecha), sa.func.max(t.c.fecha), sa.func.count(),
                  sa.func.count(sa.distinct(t.c.ad_id))).where(t.c.cliente == cliente)
    with db.conectar() as con:
        desde, hasta, filas, anuncios = con.execute(q).one()
    return {"desde": desde, "hasta": hasta, "filas": int(filas or 0), "anuncios": int(anuncios or 0)}


def hay_tienda(cliente):
    t = db.tw_tienda_dia
    with db.conectar() as con:
        return bool(con.execute(sa.select(t.c.id).where(t.c.cliente == cliente).limit(1)).first())


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


def canales(cliente, desde, hasta):
    """Canales con gasto o impresiones en el rango, del que más gastó al que menos."""
    t = db.tw_anuncio_dia
    q = (sa.select(t.c.canal).where(t.c.cliente == cliente, t.c.fecha >= desde, t.c.fecha <= hasta)
         .group_by(t.c.canal).having(sa.or_(sa.func.sum(t.c.gasto) > 0, sa.func.sum(t.c.impresiones) > 0))
         .order_by(sa.func.sum(t.c.gasto).desc()))
    with db.conectar() as con:
        return [r[0] for r in con.execute(q)]


def piezas_creatv(cliente, ad_ids):
    """{meta_ad_id: {"ep_id", "experimento_id", "experimento", "estado",
    "pieza_id", "tipo", "url_video", "url_miniatura"}} de los anuncios que
    lanzó Creatv (experimento_pieza + su pieza): para marcarlos en la
    evaluación, pausarlos/activarlos desde la pestaña y mandar a Claude los
    fotogramas del video real (que vive en R2) en vez de la miniatura."""
    ids = [str(a) for a in ad_ids if a]
    if not ids:
        return {}
    ep, ex, pz = db.experimento_pieza, db.experimento, db.pieza
    q = (sa.select(ep.c.meta_ad_id, ep.c.id, ep.c.experimento_id, ex.c.nombre, ep.c.estado, ep.c.pieza_id,
                   pz.c.tipo, pz.c.url_video, pz.c.url_miniatura)
         .select_from(ep.join(ex, ex.c.id == ep.c.experimento_id).outerjoin(pz, pz.c.id == ep.c.pieza_id))
         .where(ex.c.cliente == cliente, ep.c.meta_ad_id.in_(ids)))
    with db.conectar() as con:
        return {r[0]: {"ep_id": r[1], "experimento_id": r[2], "experimento": r[3], "estado": r[4],
                       "pieza_id": r[5], "tipo": "imagen" if r[6] == "imagen" else "video",
                       "url_video": r[7], "url_miniatura": r[8]} for r in con.execute(q)}
