"""
Biblioteca de referentes (spec 2026-09-23): anuncios reales clasificados por
etapa, consciencia, familia y dolor. ÚNICO escritor de `referente`,
`referente_familia` y `barrido`. Solo SQLAlchemy Core sobre data/creatv.db;
nada de Flask ni de proveedores.

Visibilidad: un proyecto ve los referentes globales (cliente NULL) y los
suyos. `anuncio_id` (id del Ad Library de Meta) es único global: un anuncio
que ya existe se actualiza, nunca se duplica ni cambia de dueño.
"""
import math

import sqlalchemy as sa

import db

ETAPAS = ("TOF", "MOF", "BOF")
CONSCIENCIAS = ("unaware", "problem-aware", "solution-aware", "product-aware", "most-aware")
FUENTES = ("copycoders", "atria", "apify")
CLASIFICACIONES = ("fuente", "claude", "pendiente", "error")
ESTADOS_IMAGEN = ("ok", "pendiente", "error")
TIPOS = ("imagen", "video", "carrusel")
ESTADOS_BARRIDO = ("en_cola", "trayendo", "guardando", "clasificando", "listo", "parcial", "error")
ETIQUETAS_ETAPA = {"TOF": "arriba del funnel", "MOF": "medio del funnel", "BOF": "abajo del funnel"}
ETIQUETAS_CONSCIENCIA = {"unaware": "inconsciente", "problem-aware": "consciente del problema",
                         "solution-aware": "consciente de la solución", "product-aware": "consciente del producto",
                         "most-aware": "muy consciente"}
POR_PAGINA = 60
CLIENTE_CREATV = "_creatv"

_CAMPOS_ANUNCIO = ("pagina_id", "fuente", "marca", "url_anuncio", "url_marca", "titular", "cuerpo", "idioma", "pais",
                   "tipo", "imagen_origen", "dias", "variantes", "primera_vez", "ultima_vez", "activo",
                   "etiquetas_fuente", "etapa", "consciencia", "familia", "dolor", "firma", "clasificacion", "extra")
_ACTUALIZABLES = ("dias", "variantes", "ultima_vez", "activo")
_CLASIFICACION = ("etapa", "consciencia", "familia", "dolor", "firma")
_BARRIDO_COLS = ("estado", "traidos", "nuevos", "clasificados", "pendientes", "con_imagen", "usd_estimado", "usd_real",
                 "llamadas_fuente", "tarea_id", "aviso", "extra", "consulta", "tope")


class ErrorDatos(ValueError):
    """Dato inválido; el mensaje se muestra tal cual a la persona."""


def _a_dict(fila):
    return dict(fila._mapping)


def _texto(v, largo=None):
    v = (v or "").strip() if isinstance(v, str) else ("" if v is None else str(v).strip())
    return v[:largo] if largo else v


def _visible(t, cliente):
    return sa.or_(t.c.cliente.is_(None), t.c.cliente == cliente)


def _entero(v):
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- familias ---

def familia_asegurar(nombre, descripcion="", origen="copycoders"):
    nombre = _texto(nombre, 120)
    if not nombre:
        raise ErrorDatos("La familia necesita un nombre.")
    if origen not in ("copycoders", "claude", "admin"):
        raise ErrorDatos(f"Origen de familia inválido: {origen}")
    descripcion = _texto(descripcion)
    t = db.referente_familia
    with db.conectar() as con:
        f = con.execute(sa.select(t).where(t.c.nombre == nombre)).first()
        if f:
            if descripcion and not (f.descripcion or "").strip():
                con.execute(t.update().where(t.c.id == f.id).values(descripcion=descripcion))
            return f.id
        return con.execute(t.insert().values(nombre=nombre, descripcion=descripcion, origen=origen,
                                             creado_en=db.ahora())).inserted_primary_key[0]


def familias(cliente=None):
    t, r = db.referente_familia, db.referente
    conteo = (sa.select(r.c.familia, sa.func.count().label("n"))
              .where(_visible(r, cliente), r.c.estado_imagen == "ok").group_by(r.c.familia).subquery())
    q = (sa.select(t, sa.func.coalesce(conteo.c.n, 0).label("n"))
         .select_from(t.outerjoin(conteo, conteo.c.familia == t.c.nombre)).order_by(t.c.nombre))
    with db.conectar() as con:
        return [_a_dict(f) for f in con.execute(q)]


def familia_actualizar(familia_id, descripcion):
    t = db.referente_familia
    with db.conectar() as con:
        return con.execute(t.update().where(t.c.id == familia_id).values(descripcion=_texto(descripcion))).rowcount == 1


# -------------------------------------------------------------- referentes ---

def _validar_anuncio(a):
    if not _texto(a.get("anuncio_id"), 40):
        raise ErrorDatos("El anuncio necesita anuncio_id.")
    if a.get("fuente") not in FUENTES:
        raise ErrorDatos(f"Fuente desconocida: {a.get('fuente')}")
    if not _texto(a.get("imagen_origen")):
        raise ErrorDatos("El anuncio necesita imagen_origen.")
    if a.get("tipo") not in (None, "") + TIPOS:
        raise ErrorDatos(f"Tipo inválido: {a.get('tipo')}")
    if a.get("etapa") not in (None, "") + ETAPAS:
        raise ErrorDatos(f"Etapa inválida: {a.get('etapa')}")
    if a.get("consciencia") not in (None, "") + CONSCIENCIAS:
        raise ErrorDatos(f"Consciencia inválida: {a.get('consciencia')}")
    if a.get("clasificacion") not in (None, "") + CLASIFICACIONES:
        raise ErrorDatos(f"Clasificación inválida: {a.get('clasificacion')}")


def guardar_referente(anuncio, cliente=None, barrido_id=None):
    """Upsert por anuncio_id. Devuelve (id, creado). Si ya existe: actualiza
    dias/variantes/ultima_vez/activo (y cuerpo si estaba vacío); si estaba sin
    clasificar y la fuente trae clasificación, la toma; nunca cambia `cliente`."""
    a = dict(anuncio)
    _validar_anuncio(a)
    aid = _texto(a["anuncio_id"], 40)
    ahora = db.ahora()
    t = db.referente
    with db.conectar() as con:
        fila = con.execute(sa.select(t).where(t.c.anuncio_id == aid)).first()
        if fila:
            cambios = {k: a[k] for k in _ACTUALIZABLES if a.get(k) is not None}
            if not (fila.cuerpo or "").strip() and _texto(a.get("cuerpo")):
                cambios["cuerpo"] = _texto(a["cuerpo"])
            if fila.clasificacion in ("pendiente", "error") and a.get("clasificacion") == "fuente":
                cambios.update({k: a.get(k) for k in _CLASIFICACION})
                cambios["clasificacion"] = "fuente"
            con.execute(t.update().where(t.c.id == fila.id).values(actualizado_en=ahora, **cambios))
            return fila.id, False
        valores = {k: a.get(k) for k in _CAMPOS_ANUNCIO}
        valores.update(anuncio_id=aid, cliente=cliente, barrido_id=barrido_id, creado_en=ahora, actualizado_en=ahora,
                       tipo=a.get("tipo") or "imagen", estado_imagen="pendiente",
                       clasificacion=a.get("clasificacion") or "pendiente",
                       etiquetas_fuente=a.get("etiquetas_fuente") or {}, extra=a.get("extra") or {},
                       dias=_entero(a.get("dias")), variantes=_entero(a.get("variantes")),
                       marca=_texto(a.get("marca"), 160), titular=_texto(a.get("titular")), cuerpo=_texto(a.get("cuerpo")),
                       familia=_texto(a.get("familia"), 120) or None, dolor=_texto(a.get("dolor"), 120) or None,
                       firma=_texto(a.get("firma")) or None)
        return con.execute(t.insert().values(**valores)).inserted_primary_key[0], True


def referente(cliente, referente_id):
    t = db.referente
    with db.conectar() as con:
        f = con.execute(sa.select(t).where(t.c.id == referente_id, _visible(t, cliente))).first()
        return _a_dict(f) if f else None
