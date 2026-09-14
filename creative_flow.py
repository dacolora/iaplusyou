"""
Estado de Crear (FlowPlus). Misma API de dicts de siempre (cargar/crear/
actualizar/eliminar/guardar por cliente) pero guardada en la base del motor:
una sesión cf_... = un `concepto` (idea + referencias) con una `pieza` tipo
clon_limpio (el video/imagen generado). Los campos legado sin columna propia
viven en `extra` de cada tabla. El JSON creative_flow_pendientes.json ya no se
escribe: queda como respaldo de solo lectura (ver migrar_json_a_db.py).
"""
from datetime import datetime

import sqlalchemy as sa

import db

MODOS_VALIDOS = ("A", "B")

# Campos del dict legado que van a columnas propias
_CONCEPTO_COLS = {"enfoque": "enfoque"}
_PIEZA_COLS = {"modelo": "modelo", "video_url": "url_video", "video_local": "url_local",
               "aspect_ratio": "aspect_ratio", "usd": "costo_usd", "error": "error", "tipo": "tipo"}
_ESTADO_A_PIEZA = {"prompt_pendiente": "pendiente", "prompt_listo": "pendiente",
                   "video_generando": "generando", "video_listo": "listo", "error": "error"}
_PIEZA_A_ESTADO = {v: k for k, v in _ESTADO_A_PIEZA.items()}
_PIEZA_A_ESTADO["pendiente"] = "prompt_listo"


class _Cols:
    """Acceso por nombre a las columnas de UNA tabla dentro de una fila de join."""
    def __init__(self, fila, tabla):
        self._m = fila._mapping
        self._t = tabla

    def __getattr__(self, nombre):
        return self._m[getattr(self._t.c, nombre)]


def _a_dict(c, p):
    e = dict(c.extra or {})
    e.update(p.extra or {})
    e.update({
        "accion_central": e.get("accion_central"),
        "enfoque": c.enfoque,
        "referencias_urls": e.get("referencias_urls"),
        "referencias": e.get("referencias"),
        "estado": e.get("estado_legado") or _PIEZA_A_ESTADO.get(p.estado, p.estado),
        "modelo": p.modelo, "video_url": p.url_video, "video_local": p.url_local,
        "aspect_ratio": p.aspect_ratio, "usd": p.costo_usd, "error": p.error,
        "tipo": p.tipo if p.tipo in ("video", "imagen") else e.get("tipo", "video"),
        "duracion_objetivo": e.get("duracion_objetivo") or (int(p.duracion_s) if p.duracion_s else None),
        "creado_en": c.creado_en,
    })
    e.pop("estado_legado", None)
    return e


def _separar(campos):
    """dict legado -> (valores concepto, valores pieza, extra)."""
    vc, vp, extra = {}, {}, {}
    for k, v in campos.items():
        if k in _CONCEPTO_COLS:
            vc[_CONCEPTO_COLS[k]] = v
        elif k == "tipo":
            vp["extra_tipo"] = v
        elif k in _PIEZA_COLS:
            vp[_PIEZA_COLS[k]] = v
        elif k == "estado":
            vp["estado"] = _ESTADO_A_PIEZA.get(v, "pendiente")
            extra["estado_legado"] = v
        elif k == "duracion_objetivo":
            vp["duracion_s"] = float(v or 0)
            extra[k] = v
        else:
            extra[k] = v
    return vc, vp, extra


def cargar(cliente):
    q = (sa.select(db.concepto, db.pieza)
         .join(db.pieza, db.pieza.c.concepto_id == db.concepto.c.id)
         .where(db.concepto.c.cliente == cliente, db.pieza.c.tipo != "final",
                db.concepto.c.legado_id.isnot(None))
         .order_by(db.concepto.c.id))
    with db.conectar() as con:
        filas = con.execute(q).fetchall()
    return {f._mapping[db.concepto.c.legado_id]: _a_dict(_Cols(f, db.concepto), _Cols(f, db.pieza)) for f in filas}


def crear(cliente, personajes_ids, productos_ids, escenas_ids, accion_central,
          duracion_objetivo, tono, modo, referencias_urls=None, platforms=None,
          legado_id=None, creado_en=None):
    if modo not in MODOS_VALIDOS:
        raise ValueError(f"Modo inválido: {modo}. Opciones: {MODOS_VALIDOS}")
    cf_id = legado_id or ("cf_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
    ahora = creado_en[:19] if creado_en else db.ahora()
    extra = {"personajes_ids": personajes_ids, "productos_ids": productos_ids, "escenas_ids": escenas_ids,
             "accion_central": accion_central, "duracion_objetivo": duracion_objetivo, "tono": tono, "modo": modo,
             "platforms": platforms or [], "prompt_relleno": None, "referencias_urls": referencias_urls,
             "credits": None, "estado_legado": "prompt_pendiente"}
    with db.conectar() as con:
        cid = con.execute(db.concepto.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, origen="manual",
            legado_id=cf_id, extra=extra)).inserted_primary_key[0]
        con.execute(db.pieza.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, concepto_id=cid, tipo="video",
            estado="pendiente", duracion_s=float(duracion_objetivo or 0), legado_id=cf_id, extra={}))
    return cf_id


def _ids(con, cliente, cf_id):
    f = con.execute(sa.select(db.concepto.c.id, db.pieza.c.id, db.concepto.c.extra, db.pieza.c.extra)
                    .join(db.pieza, db.pieza.c.concepto_id == db.concepto.c.id)
                    .where(db.concepto.c.cliente == cliente, db.concepto.c.legado_id == cf_id,
                           db.pieza.c.tipo != "final")
                    .order_by(db.pieza.c.id)).first()
    return f


def actualizar(cliente, cf_id, **campos):
    with db.conectar() as con:
        f = _ids(con, cliente, cf_id)
        if not f:
            return False
        cid, pid, extra_c, extra_p = f
        vc, vp, extra = _separar(campos)
        tipo_extra = vp.pop("extra_tipo", None)
        if tipo_extra:
            vp["tipo"] = tipo_extra
        nuevo_extra = dict(extra_c or {})
        nuevo_extra.update(extra)
        ahora = db.ahora()
        con.execute(db.concepto.update().where(db.concepto.c.id == cid).values(actualizado_en=ahora, extra=nuevo_extra, **vc))
        con.execute(db.pieza.update().where(db.pieza.c.id == pid).values(actualizado_en=ahora, **vp))
    return True


def eliminar(cliente, cf_id):
    with db.conectar() as con:
        f = _ids(con, cliente, cf_id)
        if not f:
            return False
        cid, pid = f[0], f[1]
        con.execute(db.pieza.delete().where(db.pieza.c.id == pid))
        restantes = con.execute(
            sa.select(sa.func.count()).select_from(db.pieza).where(db.pieza.c.concepto_id == cid)
        ).scalar()
        if not restantes:
            con.execute(db.concepto.delete().where(db.concepto.c.id == cid))
    return True


def guardar(cliente, data):
    """Compatibilidad: quien cargó el dict completo y lo modificó. Actualiza
    cada entrada; las que no existan se crean con lo mínimo."""
    actuales = cargar(cliente)
    for cf_id, entry in data.items():
        if cf_id in actuales:
            actualizar(cliente, cf_id, **entry)
        else:
            nuevo = crear(cliente, entry.get("personajes_ids", []), entry.get("productos_ids", []),
                          entry.get("escenas_ids", []), entry.get("accion_central", ""),
                          entry.get("duracion_objetivo", 10), entry.get("tono", ""), entry.get("modo", "A"),
                          referencias_urls=entry.get("referencias_urls"), platforms=entry.get("platforms"))
            with db.conectar() as con:
                con.execute(db.concepto.update().where(db.concepto.c.legado_id == nuevo).values(legado_id=cf_id))
                con.execute(db.pieza.update().where(db.pieza.c.legado_id == nuevo).values(legado_id=cf_id))
            actualizar(cliente, cf_id, **entry)
    for cf_id in set(actuales) - set(data):
        eliminar(cliente, cf_id)
