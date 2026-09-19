"""
Datos del módulo Nicho (spec §2): estudios, comentarios y avatares. ÚNICO
escritor de las tres tablas. Solo SQLAlchemy Core sobre data/creatv.db; nada
de Flask ni de proveedores. Aprobar un sub-avatar crea o actualiza una persona
de Sprints (origen `investigada`) a través de `sprints.datos`, que sigue siendo
el único escritor de `persona`.
"""
import re

import sqlalchemy as sa

import cola
import db
from sprints import datos as sprints_datos
from sprints.sugerencias import COLORES

ESTADOS_ESTUDIO = ("armando", "generando", "revisando")
FUENTES = ("texto", "csv", "reddit", "youtube", "apify")
TIPOS_AVATAR = ("nucleo", "sub")
BASES = ("emocion", "experiencia_producto")
ESTADOS_AVATAR = ("propuesto", "aprobado", "descartado")
NIVELES_CONCIENCIA = ("inconsciente", "consciente_del_problema", "consciente_de_la_solucion",
                      "consciente_del_producto", "muy_consciente")
CLAVES_IDENTIDAD = ("quiere_que_vean", "cree_de_si", "quiere_lograr")
MAX_RECOLECCIONES = 20          # registros que se conservan en estudio.extra["recolecciones"]

_ESTUDIO_COLS = ("nombre", "producto", "catalogo_id", "tema", "idioma", "estado", "archivado", "generacion", "extra")
_AVATAR_COLS = ("nombre", "deseo", "resumen", "demografia", "edad_rango", "emocion", "identidad", "soluciones_previas",
                "situaciones", "comportamiento", "conciencia", "encaje_producto", "tono", "palabras_clave", "evidencia",
                "sin_evidencia", "estado", "persona_id", "orden", "base", "extra")
# Lo que el formulario de revisión puede tocar (estado/persona_id van por aprobar/descartar).
AVATAR_EDITABLES = ("nombre", "deseo", "base", "demografia", "edad_rango", "emocion", "identidad", "soluciones_previas",
                    "situaciones", "comportamiento", "conciencia", "encaje_producto", "tono", "palabras_clave")
_RE_IDIOMA = re.compile(r"^[a-z]{2,5}$")


class ErrorDatos(ValueError):
    """Dato inválido; el mensaje se muestra tal cual a la persona."""


def job_id_generar(cliente, estudio_id):
    """Un solo trabajo de generación vivo por estudio (spec §7): la ruta y la
    tarea usan este mismo id, y `recalcular` lo consulta en la cola."""
    return f"nicho:{cliente}:{int(estudio_id)}:generar"


# ------------------------------------------------------------ helpers ---

def _a_dict(fila):
    return dict(fila._mapping)


def _fila(con, tabla, fila_id, cliente):
    return con.execute(sa.select(tabla).where(tabla.c.id == fila_id, tabla.c.cliente == cliente)).first()


def _actualizar(con, tabla, fila_id, cliente, permitidas, campos):
    malos = set(campos) - set(permitidas)
    if malos:
        raise ErrorDatos(f"Campos no editables: {', '.join(sorted(malos))}")
    r = con.execute(tabla.update().where(tabla.c.id == fila_id, tabla.c.cliente == cliente)
                    .values(actualizado_en=db.ahora(), **campos))
    return r.rowcount == 1


def _bloquear(con, tabla, fila_id, cliente):
    """Toma el lock de escritura de SQLite ANTES de leer (semántica de
    `BEGIN IMMEDIATE`), igual que `experimentos._bloquear`: un UPDATE sin
    efecto obliga al driver a abrir la transacción ya, así el SELECT que sigue
    ve lo que dejó el último escritor (gunicorn y el worker escriben `extra`
    a la vez). Devuelve True si la fila existe."""
    r = con.execute(tabla.update().where(tabla.c.id == fila_id, tabla.c.cliente == cliente)
                    .values(actualizado_en=tabla.c.actualizado_en))
    return r.rowcount == 1


def _texto(v, largo=None):
    v = (v or "").strip() if isinstance(v, str) else ("" if v is None else str(v).strip())
    return v[:largo] if largo else v


def _idioma(v):
    v = (v or "").strip().lower()
    return v if _RE_IDIOMA.match(v) else "es"


# ----------------------------------------------------------- estudios ---

def crear_estudio(cliente, nombre, producto="", tema="", idioma="es", catalogo_id=None):
    nombre = _texto(nombre, 120)
    if not nombre:
        raise ErrorDatos("El estudio necesita un nombre.")
    ahora = db.ahora()
    with db.conectar() as con:
        return con.execute(db.estudio.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, nombre=nombre, producto=_texto(producto),
            catalogo_id=_texto(catalogo_id, 80) or None, tema=_texto(tema), idioma=_idioma(idioma), estado="armando",
            archivado=False, generacion=0, extra={})).inserted_primary_key[0]


def actualizar_estudio(cliente, estudio_id, /, **campos):
    if "nombre" in campos:
        campos["nombre"] = _texto(campos["nombre"], 120)
        if not campos["nombre"]:
            raise ErrorDatos("El estudio necesita un nombre.")
    if "idioma" in campos:
        campos["idioma"] = _idioma(campos["idioma"])
    if "estado" in campos and campos["estado"] not in ESTADOS_ESTUDIO:
        raise ErrorDatos(f"Estado de estudio inválido: {campos['estado']}")
    for k in ("producto", "tema"):
        if k in campos:
            campos[k] = _texto(campos[k])
    if "catalogo_id" in campos:
        campos["catalogo_id"] = _texto(campos["catalogo_id"], 80) or None
    with db.conectar() as con:
        return _actualizar(con, db.estudio, estudio_id, cliente, _ESTUDIO_COLS, campos)


def archivar_estudio(cliente, estudio_id, archivado=True):
    return actualizar_estudio(cliente, estudio_id, archivado=bool(archivado))


def actualizar_extra_estudio(cliente, estudio_id, fn):
    """Read-modify-write atómico de `estudio.extra` (lock antes de leer, una
    transacción). `fn(extra) -> extra`. Devuelve el extra escrito o None."""
    with db.conectar() as con:
        if not _bloquear(con, db.estudio, estudio_id, cliente):
            return None
        f = _fila(con, db.estudio, estudio_id, cliente)
        if not f:
            return None
        extra = fn(dict(f.extra or {}))
        con.execute(db.estudio.update().where(db.estudio.c.id == estudio_id)
                    .values(actualizado_en=db.ahora(), extra=extra))
        return extra


def registrar_recoleccion(cliente, estudio_id, registro):
    """Anota una recolección (fuente, nuevos, repetidos, aviso) con fecha en
    `extra.recolecciones`; conserva las últimas MAX_RECOLECCIONES."""
    entrada = {**dict(registro or {}), "fecha": db.ahora()}

    def _fn(extra):
        lista = list(extra.get("recolecciones") or []) + [entrada]
        return {**extra, "recolecciones": lista[-MAX_RECOLECCIONES:]}
    return actualizar_extra_estudio(cliente, estudio_id, _fn)


def _conteos(con, cliente, ids):
    """Por estudio: comentarios por fuente (con excluidos) y sub-avatares por estado."""
    c, a = db.comentario, db.avatar
    fuentes, aprobados, subs = {}, {}, {}
    if not ids:
        return fuentes, aprobados, subs
    excluidos = sa.func.sum(sa.case((c.c.excluido.is_(True), 1), else_=0))
    for eid, fuente, n, exc in con.execute(
            sa.select(c.c.estudio_id, c.c.fuente, sa.func.count(), excluidos)
            .where(c.c.cliente == cliente, c.c.estudio_id.in_(ids)).group_by(c.c.estudio_id, c.c.fuente)):
        fuentes.setdefault(eid, {})[fuente] = {"total": int(n), "excluidos": int(exc or 0)}
    for eid, estado, n in con.execute(
            sa.select(a.c.estudio_id, a.c.estado, sa.func.count())
            .where(a.c.cliente == cliente, a.c.estudio_id.in_(ids), a.c.tipo == "sub").group_by(a.c.estudio_id, a.c.estado)):
        if estado == "aprobado":
            aprobados[eid] = int(n)
        if estado != "descartado":
            subs[eid] = subs.get(eid, 0) + int(n)
    return fuentes, aprobados, subs


def _decorar(e, fuentes, aprobados, subs):
    por_fuente = fuentes.get(e["id"], {})
    total = sum(v["total"] for v in por_fuente.values())
    e["comentarios_total"] = total
    e["comentarios_activos"] = total - sum(v["excluidos"] for v in por_fuente.values())
    e["fuentes"] = por_fuente
    e["avatares_aprobados"] = aprobados.get(e["id"], 0)
    e["avatares_total"] = subs.get(e["id"], 0)
    e["extra"] = dict(e.get("extra") or {})
    return e


def estudios(cliente, incluir_archivados=False):
    t = db.estudio
    q = sa.select(t).where(t.c.cliente == cliente)
    if not incluir_archivados:
        q = q.where(t.c.archivado.is_(False))
    with db.conectar() as con:
        lista = [_a_dict(f) for f in con.execute(q.order_by(t.c.id.desc()))]
        fuentes, aprobados, subs = _conteos(con, cliente, [e["id"] for e in lista])
    return [_decorar(e, fuentes, aprobados, subs) for e in lista]


def estudio(cliente, estudio_id):
    with db.conectar() as con:
        f = _fila(con, db.estudio, estudio_id, cliente)
        if not f:
            return None
        fuentes, aprobados, subs = _conteos(con, cliente, [f.id])
    return _decorar(_a_dict(f), fuentes, aprobados, subs)


def recalcular(cliente, estudio_id, tarea_viva=None):
    """Re-deriva `estudio.estado` (spec §1): `generando` si hay una tarea viva
    con el job_id de generación (consultado en la cola salvo que el llamador
    ya lo sepa: la tarea misma pasa `tarea_viva=False` al terminar, porque
    desde adentro su fila sigue `en_curso`); si no, `revisando` cuando el
    estudio tiene algún avatar; si no, `armando`. Devuelve el estado o None."""
    if tarea_viva is None:
        fila = cola.consultar_por_job(job_id_generar(cliente, estudio_id))
        tarea_viva = bool(fila and fila["estado"] in ("pendiente", "en_curso"))
    with db.conectar() as con:
        f = _fila(con, db.estudio, estudio_id, cliente)
        if not f:
            return None
        n = con.execute(sa.select(sa.func.count()).select_from(db.avatar).where(
            db.avatar.c.estudio_id == estudio_id, db.avatar.c.cliente == cliente)).scalar() or 0
        nuevo = "generando" if tarea_viva else ("revisando" if n else "armando")
        if nuevo != f.estado:
            con.execute(db.estudio.update().where(db.estudio.c.id == estudio_id)
                        .values(actualizado_en=db.ahora(), estado=nuevo))
    return nuevo


# -------------------------------------------------------- comentarios ---

def agregar_comentarios(cliente, estudio_id, fuente, lista):
    """Inserta comentarios ya normalizados (`nicho.fuentes.base.normalizar_comentario`)
    en UNA transacción con `INSERT OR IGNORE` sobre `uq_comentario_fuente`:
    los repetidos no duplican. Un dict sin texto o sin fuente_id se salta."""
    if fuente not in FUENTES:
        raise ErrorDatos(f"Fuente desconocida: {fuente}")
    ahora = db.ahora()
    nuevos = repetidos = 0
    with db.conectar() as con:
        if not _fila(con, db.estudio, estudio_id, cliente):
            raise ErrorDatos("Ese estudio no existe.")
        for c in lista or []:
            texto = _texto((c or {}).get("texto"))
            fuente_id = _texto((c or {}).get("fuente_id"), 120)
            if not texto or not fuente_id:
                continue
            r = con.execute(db.comentario.insert().prefix_with("OR IGNORE").values(
                cliente=cliente, creado_en=ahora, actualizado_en=ahora, estudio_id=estudio_id, fuente=fuente,
                fuente_id=fuente_id, texto=texto[:2000], url=_texto(c.get("url"), 500) or None,
                contexto=_texto(c.get("contexto"), 300) or None, puntuacion=c.get("puntuacion"),
                fecha=_texto(c.get("fecha"), 19) or None, excluido=False,
                extra=dict(c.get("extra")) if isinstance(c.get("extra"), dict) else {}))
            if r.rowcount == 1:
                nuevos += 1
            else:
                repetidos += 1
    return {"nuevos": nuevos, "repetidos": repetidos}


def comentarios(cliente, estudio_id, fuente=None, pagina=1, por_pagina=50):
    """Página de comentarios, más nuevo primero (incluye excluidos, con su bandera)."""
    c = db.comentario
    cond = [c.c.cliente == cliente, c.c.estudio_id == estudio_id]
    if fuente:
        cond.append(c.c.fuente == fuente)
    pagina = max(1, int(pagina or 1))
    por_pagina = max(1, min(200, int(por_pagina or 50)))
    with db.conectar() as con:
        total = int(con.execute(sa.select(sa.func.count()).select_from(c).where(*cond)).scalar() or 0)
        filas = con.execute(sa.select(c).where(*cond).order_by(c.c.id.desc())
                            .limit(por_pagina).offset((pagina - 1) * por_pagina)).all()
    return {"items": [_a_dict(f) for f in filas], "total": total, "pagina": pagina,
            "paginas": max(1, -(-total // por_pagina))}


def comentario(cliente, comentario_id):
    with db.conectar() as con:
        f = _fila(con, db.comentario, comentario_id, cliente)
    return _a_dict(f) if f else None


def comentarios_para_generar(cliente, estudio_id):
    """Los que entran a Claude: no excluidos, en orden de id."""
    c = db.comentario
    with db.conectar() as con:
        return [_a_dict(f) for f in con.execute(sa.select(c).where(
            c.c.cliente == cliente, c.c.estudio_id == estudio_id, c.c.excluido.is_(False)).order_by(c.c.id))]


def contar_por_fuente(cliente, estudio_id):
    with db.conectar() as con:
        fuentes, _, _ = _conteos(con, cliente, [estudio_id])
    return fuentes.get(estudio_id, {})


def excluir_comentario(cliente, comentario_id, excluido=True):
    with db.conectar() as con:
        r = con.execute(db.comentario.update().where(
            db.comentario.c.id == comentario_id, db.comentario.c.cliente == cliente)
            .values(actualizado_en=db.ahora(), excluido=bool(excluido)))
    return r.rowcount == 1


def borrar_fuente(cliente, estudio_id, fuente):
    """Borra todos los comentarios de una fuente en el estudio; devuelve cuántos."""
    with db.conectar() as con:
        r = con.execute(db.comentario.delete().where(
            db.comentario.c.cliente == cliente, db.comentario.c.estudio_id == estudio_id, db.comentario.c.fuente == fuente))
    return int(r.rowcount or 0)
