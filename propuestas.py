"""
Propuestas del decisor (Bloque 4): acciones que el motor recomienda pero que,
por el modo del experimento o por tope alcanzado, esperan aprobación humana.
Solo datos (tabla `propuesta`); quien ejecuta una propuesta aprobada es
acciones.ejecutar desde la ruta, y luego la marca `ejecutada`.

Estados: pendiente → aprobada | rechazada; aprobada → ejecutada.
"""
import sqlalchemy as sa

import db

ESTADOS = ("pendiente", "aprobada", "rechazada", "ejecutada")
_CLAVES_DEDUPE = ("ep_id", "pais")


def _a_dict(f):
    m = f._mapping
    p = db.propuesta
    return {"id": m[p.c.id], "experimento_id": m[p.c.experimento_id], "accion": m[p.c.accion],
            "payload": m[p.c.payload] or {}, "estado": m[p.c.estado], "creado_en": m[p.c.creado_en],
            "resuelta_en": m[p.c.resuelta_en]}


def _clave(payload):
    """(ep_id, pais, ep_ids ordenados): dos propuestas `activar` con listas
    de piezas distintas son cosas distintas (I-4) — antes None == None las
    fundía y la segunda derivación lista nunca pedía activarse."""
    return tuple(payload.get(k) for k in _CLAVES_DEDUPE) + (tuple(sorted(payload.get("ep_ids") or [])),)


def _misma_cosa(a, b):
    return _clave(a) == _clave(b)


def crear(cliente, experimento_id, accion, payload, motivo):
    """Crea una propuesta pendiente y devuelve su id. Si ya hay una pendiente
    con la misma acción sobre la misma pieza/país/lista de piezas (payload
    ep_id/pais/ep_ids), no duplica: devuelve la existente."""
    payload = dict(payload or {})
    payload["motivo"] = motivo
    with db.conectar() as con:
        p = db.propuesta
        for f in con.execute(sa.select(p).where(
                p.c.cliente == cliente, p.c.experimento_id == experimento_id,
                p.c.accion == accion, p.c.estado == "pendiente").order_by(p.c.id)):
            if _misma_cosa(f._mapping[p.c.payload] or {}, payload):
                return f._mapping[p.c.id]
        ahora = db.ahora()
        return con.execute(p.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, experimento_id=experimento_id,
            accion=accion, payload=payload, estado="pendiente")).inserted_primary_key[0]


def _listar(con, cliente, experimento_id, estado):
    p = db.propuesta
    q = sa.select(p).where(p.c.cliente == cliente, p.c.estado == estado)
    if experimento_id is not None:
        q = q.where(p.c.experimento_id == experimento_id)
    return [_a_dict(f) for f in con.execute(q.order_by(p.c.id))]


def pendientes(cliente, experimento_id=None):
    with db.conectar() as con:
        return _listar(con, cliente, experimento_id, "pendiente")


def obtener(cliente, propuesta_id):
    with db.conectar() as con:
        p = db.propuesta
        f = con.execute(sa.select(p).where(p.c.id == propuesta_id, p.c.cliente == cliente)).first()
        return _a_dict(f) if f else None


def _cambiar_estado(con, cliente, propuesta_id, desde, hacia):
    """Transición atómica desde→hacia; devuelve el dict nuevo o None si la
    propuesta no existe / no estaba en `desde` (ya resuelta, por ejemplo)."""
    p = db.propuesta
    ahora = db.ahora()
    r = con.execute(p.update().where(
        p.c.id == propuesta_id, p.c.cliente == cliente, p.c.estado == desde)
        .values(estado=hacia, resuelta_en=ahora, actualizado_en=ahora))
    if r.rowcount != 1:
        return None
    f = con.execute(sa.select(p).where(p.c.id == propuesta_id)).first()
    return _a_dict(f)


def resolver(cliente, propuesta_id, estado):
    """Aprueba o rechaza una propuesta pendiente. None si no existe o ya
    estaba resuelta (no se puede cambiar de opinión sobre algo resuelto)."""
    if estado not in ("aprobada", "rechazada"):
        raise ValueError("Una propuesta se resuelve como 'aprobada' o 'rechazada'.")
    with db.conectar() as con:
        return _cambiar_estado(con, cliente, propuesta_id, "pendiente", estado)


def marcar_ejecutada(cliente, propuesta_id):
    """Aprobada → ejecutada (después de acciones.ejecutar). También acepta
    una pendiente, por si la ruta ejecuta y marca en un solo paso."""
    with db.conectar() as con:
        return (_cambiar_estado(con, cliente, propuesta_id, "aprobada", "ejecutada")
                or _cambiar_estado(con, cliente, propuesta_id, "pendiente", "ejecutada"))


def reabrir(cliente, propuesta_id):
    """Aprobada → pendiente: cuando la ruta aprobó pero acciones.ejecutar
    falló, la propuesta vuelve a la lista para reintentarla o rechazarla.
    Atómico (UPDATE ... WHERE estado='aprobada'); None si no estaba aprobada."""
    with db.conectar() as con:
        return _cambiar_estado(con, cliente, propuesta_id, "aprobada", "pendiente")


def aprobar_todas(cliente, experimento_id):
    """Aprueba todas las pendientes de un experimento; devuelve las aprobadas
    en orden de creación."""
    with db.conectar() as con:
        out = []
        for pr in _listar(con, cliente, experimento_id, "pendiente"):
            r = _cambiar_estado(con, cliente, pr["id"], "pendiente", "aprobada")
            if r:
                out.append(r)
        return out

