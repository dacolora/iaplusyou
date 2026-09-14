"""
Estado de Campañas (anuncios en Meta). Misma API de dicts de siempre — el
"contrato Enviar a Publicidad" (crear/cargar/actualizar/eliminar) — guardada en
la base del motor: cada ad_... es una fila de `experimento_pieza` dentro del
experimento legado del cliente ("Anuncios sueltos"); las métricas son filas de
`metrica_snapshot` (se conserva historial; el dict devuelve la última).
ads.json queda como respaldo de solo lectura.
"""
from datetime import datetime

import sqlalchemy as sa

import db

_METRICAS_VACIAS = {"impresiones": 0, "clics": 0, "gasto_usd": 0.0, "ctr": 0.0, "actualizado_en": None}
# Columnas int en metrica_snapshot (el resto de _SNAP_COLS son float)
_SNAP_COLS_INT = {"impresiones", "reach", "clics", "clics_enlace", "compras"}
_SNAP_COLS = {"impresiones": "impresiones", "reach": "alcance", "frecuencia": "frecuencia", "clics": "clics",
              "clics_enlace": "clics_enlace", "ctr": "ctr", "cpc": "cpc", "cpm": "cpm", "gasto_usd": "gasto",
              "compras": "compras", "ingresos": "ingresos", "roas": "roas", "costo_por_resultado": "cpa"}
_SNAP_INV = {v: k for k, v in _SNAP_COLS.items()}
_META_IDS = ("campaign_id", "adset_id", "ad_id", "creative_id")


def _experimento_legado(con, cliente):
    eid = con.execute(sa.select(db.experimento.c.id).where(
        db.experimento.c.cliente == cliente, db.experimento.c.legado.is_(True))).scalar()
    if eid:
        return eid
    ahora = db.ahora()
    return con.execute(db.experimento.insert().values(
        cliente=cliente, creado_en=ahora, actualizado_en=ahora, nombre="Anuncios sueltos",
        modo="manual", estado="corriendo", legado=True)).inserted_primary_key[0]


def _ultima_metrica(con, epid):
    f = con.execute(sa.select(db.metrica_snapshot).where(db.metrica_snapshot.c.experimento_pieza_id == epid)
                    .order_by(db.metrica_snapshot.c.id.desc()).limit(1)).first()
    if not f:
        return dict(_METRICAS_VACIAS)
    m = f._mapping
    out = {k: m[db.metrica_snapshot.c[col]] for col, k in _SNAP_INV.items()}
    out.update(m[db.metrica_snapshot.c.extra] or {})
    out["actualizado_en"] = m[db.metrica_snapshot.c.tomado_en]
    return out


def _a_dict(con, f):
    m = f._mapping
    extra = m[db.experimento_pieza.c.extra] or {}
    e = dict(extra)
    e.pop("campaign_id", None)
    e.update({
        "estado": m[db.experimento_pieza.c.estado],
        "error": m[db.experimento_pieza.c.error],
        "meta_ids": {
            "campaign_id": extra.get("campaign_id"),
            "adset_id": m[db.experimento_pieza.c.meta_adset_id],
            "ad_id": m[db.experimento_pieza.c.meta_ad_id],
            "creative_id": m[db.experimento_pieza.c.meta_creative_id],
        },
        "metricas": _ultima_metrica(con, m[db.experimento_pieza.c.id]),
        "creado_en": m[db.experimento_pieza.c.creado_en],
    })
    return e


def cargar(cliente):
    with db.conectar() as con:
        filas = con.execute(sa.select(db.experimento_pieza).where(
            db.experimento_pieza.c.cliente == cliente, db.experimento_pieza.c.legado_id.isnot(None)
        ).order_by(db.experimento_pieza.c.id)).fetchall()
        return {f._mapping[db.experimento_pieza.c.legado_id]: _a_dict(con, f) for f in filas}


def crear(cliente, fuente, fuente_id, contenido_url, contenido_tipo, nombre):
    ad_id = "ad_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    ahora = db.ahora()
    extra = {"fuente": fuente, "fuente_id": fuente_id, "contenido_url": contenido_url, "contenido_tipo": contenido_tipo,
             "nombre": nombre, "objetivo": None, "presupuesto_diario_usd": None, "dias": None, "audiencia": None,
             "campaign_id": None}
    with db.conectar() as con:
        eid = _experimento_legado(con, cliente)
        con.execute(db.experimento_pieza.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, experimento_id=eid, estado="en_cola",
            legado_id=ad_id, extra=extra))
    return ad_id


def _fila(con, cliente, ad_id):
    f = con.execute(sa.select(db.experimento_pieza).where(
        db.experimento_pieza.c.cliente == cliente, db.experimento_pieza.c.legado_id == ad_id)).first()
    if not f:
        raise KeyError(f"No existe el anuncio {ad_id} para {cliente}")
    return f


def actualizar(cliente, ad_id, **campos):
    with db.conectar() as con:
        f = _fila(con, cliente, ad_id)
        epid = f._mapping[db.experimento_pieza.c.id]
        extra = dict(f._mapping[db.experimento_pieza.c.extra] or {})
        valores = {"actualizado_en": db.ahora()}
        for k, v in campos.items():
            if k == "estado":
                valores["estado"] = v
            elif k == "error":
                valores["error"] = v
            elif k == "meta_ids":
                v = v or {}
                extra["campaign_id"] = v.get("campaign_id")
                valores.update(meta_adset_id=v.get("adset_id"), meta_ad_id=v.get("ad_id"), meta_creative_id=v.get("creative_id"))
            elif k == "metricas":
                m = dict(v or {})
                snap = {}
                for k2, col in _SNAP_COLS.items():
                    val = m.pop(k2, None)
                    if k2 in _SNAP_COLS_INT:
                        snap[col] = int(float(val or 0))
                    else:
                        snap[col] = float(val or 0)
                tomado = m.pop("actualizado_en", None) or db.ahora()
                estado_meta = m.get("estado_meta")
                con.execute(db.metrica_snapshot.insert().values(experimento_pieza_id=epid, tomado_en=tomado, extra=m, **snap))
                if estado_meta:
                    valores["estado_meta"] = estado_meta
            else:
                extra[k] = v
        valores["extra"] = extra
        con.execute(db.experimento_pieza.update().where(db.experimento_pieza.c.id == epid).values(**valores))


def eliminar(cliente, ad_id):
    with db.conectar() as con:
        try:
            f = _fila(con, cliente, ad_id)
        except KeyError:
            return
        epid = f._mapping[db.experimento_pieza.c.id]
        con.execute(db.metrica_snapshot.delete().where(db.metrica_snapshot.c.experimento_pieza_id == epid))
        con.execute(db.experimento_pieza.delete().where(db.experimento_pieza.c.id == epid))
