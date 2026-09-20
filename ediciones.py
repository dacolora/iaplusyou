"""Ediciones del editor (spec §5): CRUD sobre `edicion` y `edicion_version`.
El documento se valida al entrar y al salir; el autoguardado es CAS por
`version_n` (mismo patrón que `pieza_qa`): dos pestañas no se pisan."""
import sqlalchemy as sa

import db
import materiales
from final_edition import documento as documento_mod


class Conflicto(RuntimeError):
    """El documento cambió desde que se cargó (o no es de este cliente)."""


def _dict(f):
    return dict(f._mapping) if f is not None else None


def crear(cliente, tipo, nombre, documento, cf_id=None, creada_por=None):
    if tipo not in ("video", "imagen"):
        raise ValueError("tipo debe ser video o imagen")
    doc = documento_mod.validar(documento)
    ahora = db.ahora()
    with db.conectar() as con:
        r = con.execute(db.edicion.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, cf_id=cf_id, tipo=tipo,
            nombre=(nombre or "Sin nombre")[:120], documento=doc, version_n=0, estado="borrador", creada_por=creada_por))
        eid = r.inserted_primary_key[0]
    materiales.marcar_uso(doc.get("materiales") or [])
    return cargar(cliente, eid)


def cargar(cliente, edicion_id):
    with db.conectar() as con:
        f = _dict(con.execute(sa.select(db.edicion).where(
            db.edicion.c.cliente == cliente, db.edicion.c.id == int(edicion_id))).first())
    if not f:
        return None
    f["documento"] = documento_mod.validar(documento_mod.migrar(f["documento"]))
    return f


def listar(cliente, cf_id=None):
    cols = [c for c in db.edicion.c if c.name != "documento"]
    cond = [db.edicion.c.cliente == cliente]
    if cf_id:
        cond.append(db.edicion.c.cf_id == cf_id)
    with db.conectar() as con:
        return [dict(f._mapping) for f in con.execute(
            sa.select(*cols).where(*cond).order_by(db.edicion.c.actualizado_en.desc()))]


def guardar(cliente, edicion_id, documento, version_n):
    doc = documento_mod.validar(documento)
    nuevo = int(version_n) + 1
    with db.conectar() as con:
        r = con.execute(db.edicion.update().where(
            db.edicion.c.cliente == cliente, db.edicion.c.id == int(edicion_id),
            db.edicion.c.version_n == int(version_n)).values(
            documento=doc, version_n=nuevo, actualizado_en=db.ahora()))
        if r.rowcount != 1:
            raise Conflicto("La edición cambió en otra pestaña; recarga para seguir.")
    materiales.marcar_uso(doc.get("materiales") or [])
    return nuevo


def versionar(cliente, edicion_id, motivo):
    if motivo not in ("producir", "manual"):
        raise ValueError("motivo debe ser producir o manual")
    with db.conectar() as con:
        # Toma el lock de escritura ANTES de leer el MAX(n) (mismo problema y
        # misma solución que experimentos._bloquear: pysqlite deja un SELECT
        # suelto en autocommit, así que dos `versionar` concurrentes pueden
        # leer el mismo MAX y el segundo INSERT choca contra
        # uq_edicion_version_n con un IntegrityError crudo). Un UPDATE sin
        # efecto sobre la fila obliga a abrir la transacción y tomar el lock
        # RESERVED ya; con busy_timeout=5000 el segundo escritor espera en
        # vez de fallar.
        r = con.execute(db.edicion.update().where(db.edicion.c.id == int(edicion_id), db.edicion.c.cliente == cliente)
                        .values(actualizado_en=db.edicion.c.actualizado_en))
        if r.rowcount != 1:
            raise Conflicto("No existe esa edición.")
        ed = _dict(con.execute(sa.select(db.edicion).where(
            db.edicion.c.cliente == cliente, db.edicion.c.id == int(edicion_id))).first())
        n = int(con.execute(sa.select(sa.func.coalesce(sa.func.max(db.edicion_version.c.n), 0))
                            .where(db.edicion_version.c.edicion_id == ed["id"])).scalar() or 0) + 1
        r = con.execute(db.edicion_version.insert().values(
            edicion_id=ed["id"], n=n, documento=ed["documento"], motivo=motivo, creada_en=db.ahora()))
        vid = r.inserted_primary_key[0]
        return _dict(con.execute(sa.select(db.edicion_version).where(db.edicion_version.c.id == vid)).first())


def versiones(cliente, edicion_id):
    cols = [c for c in db.edicion_version.c if c.name != "documento"]
    with db.conectar() as con:
        return [dict(f._mapping) for f in con.execute(
            sa.select(*cols).join(db.edicion, db.edicion.c.id == db.edicion_version.c.edicion_id)
            .where(db.edicion.c.cliente == cliente, db.edicion.c.id == int(edicion_id))
            .order_by(db.edicion_version.c.n))]


def version(cliente, version_id):
    with db.conectar() as con:
        return _dict(con.execute(
            sa.select(db.edicion_version).join(db.edicion, db.edicion.c.id == db.edicion_version.c.edicion_id)
            .where(db.edicion.c.cliente == cliente, db.edicion_version.c.id == int(version_id))).first())


def restaurar(cliente, edicion_id, n):
    with db.conectar() as con:
        v = _dict(con.execute(
            sa.select(db.edicion_version).join(db.edicion, db.edicion.c.id == db.edicion_version.c.edicion_id)
            .where(db.edicion.c.cliente == cliente, db.edicion.c.id == int(edicion_id),
                   db.edicion_version.c.n == int(n))).first())
        if not v:
            raise Conflicto("No existe esa versión.")
        actual = int(con.execute(sa.select(db.edicion.c.version_n).where(db.edicion.c.id == int(edicion_id))).scalar())
    return guardar(cliente, edicion_id, documento_mod.migrar(v["documento"]), actual)


def apuntar_final(cliente, final_legado_id, version_id):
    """Enlaza la pieza final con la versión congelada que la produjo.
    Devuelve las filas tocadas (0 = esa final no existe para este cliente)."""
    with db.conectar() as con:
        r = con.execute(db.pieza.update().where(
            db.pieza.c.cliente == cliente, db.pieza.c.tipo == "final", db.pieza.c.legado_id == final_legado_id)
            .values(edicion_version_id=int(version_id), actualizado_en=db.ahora()))
        return r.rowcount
