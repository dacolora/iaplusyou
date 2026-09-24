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


def _condiciones(cliente, filtros):
    f = filtros or {}
    t = db.referente
    cond = [_visible(t, cliente), t.c.estado_imagen == "ok"]
    if f.get("etapa") in ETAPAS:
        cond.append(t.c.etapa == f["etapa"])
    if f.get("consciencia") in CONSCIENCIAS:
        cond.append(t.c.consciencia == f["consciencia"])
    for campo in ("familia", "dolor", "marca"):
        v = _texto(f.get(campo), 160)
        if v:
            cond.append(getattr(t.c, campo) == v)
    fuente = f.get("fuente")
    if fuente == "mios":
        cond.append(t.c.cliente == cliente)
    elif fuente in FUENTES:
        cond.append(t.c.fuente == fuente)
    q = _texto(f.get("q"), 80)
    if q:
        like = f"%{q}%"
        cond.append(sa.or_(t.c.titular.ilike(like), t.c.firma.ilike(like), t.c.marca.ilike(like)))
    return cond


def listar(cliente, filtros=None, pagina=1, por_pagina=POR_PAGINA):
    t = db.referente
    cond = _condiciones(cliente, filtros)
    por_pagina = max(1, int(por_pagina))
    with db.conectar() as con:
        total = con.execute(sa.select(sa.func.count()).select_from(t).where(*cond)).scalar() or 0
        paginas = max(1, math.ceil(total / por_pagina))
        pagina = min(max(1, _entero(pagina) or 1), paginas)
        filas = con.execute(sa.select(t).where(*cond)
                            .order_by(sa.desc(t.c.dias).nulls_last(), sa.desc(t.c.variantes).nulls_last(), t.c.id.desc())
                            .limit(por_pagina).offset((pagina - 1) * por_pagina))
        items = [_a_dict(r) for r in filas]
    return {"items": items, "total": int(total), "pagina": pagina, "paginas": paginas}


def opciones(cliente):
    t = db.referente
    base = [_visible(t, cliente), t.c.estado_imagen == "ok"]

    def _grupo(con, col):
        q = (sa.select(col, sa.func.count().label("n")).where(*base, col.isnot(None), col != "")
             .group_by(col).order_by(sa.desc("n"), col))
        return [(r[0], int(r[1])) for r in con.execute(q)]

    with db.conectar() as con:
        total = con.execute(sa.select(sa.func.count()).select_from(t).where(*base)).scalar() or 0
        return {"total": int(total), "familias": _grupo(con, t.c.familia), "marcas": _grupo(con, t.c.marca),
                "dolores": _grupo(con, t.c.dolor), "fuentes": _grupo(con, t.c.fuente)}


# ---------------------------------------------------------------- imágenes ---

def marcar_imagen(referente_id, estado, imagen_url=None):
    if estado not in ESTADOS_IMAGEN:
        raise ErrorDatos(f"Estado de imagen inválido: {estado}")
    t = db.referente
    valores = {"estado_imagen": estado, "actualizado_en": db.ahora()}
    if imagen_url:
        valores["imagen_url"] = imagen_url
    with db.conectar() as con:
        return con.execute(t.update().where(t.c.id == referente_id).values(**valores)).rowcount == 1


def pendientes_imagen(fuente=None, limite=100):
    t = db.referente
    q = sa.select(t).where(t.c.estado_imagen == "pendiente")
    if fuente:
        q = q.where(t.c.fuente == fuente)
    with db.conectar() as con:
        return [_a_dict(r) for r in con.execute(q.order_by(t.c.id).limit(limite))]


def contar_imagenes(fuente=None):
    t = db.referente
    q = sa.select(t.c.estado_imagen, sa.func.count()).group_by(t.c.estado_imagen)
    if fuente:
        q = q.where(t.c.fuente == fuente)
    conteo = {e: 0 for e in ESTADOS_IMAGEN}
    with db.conectar() as con:
        for estado, n in con.execute(q):
            if estado in conteo:
                conteo[estado] = int(n)
    return conteo


# ------------------------------------------------------------ traducciones ---

def sin_traducir(limite=100):
    t = db.referente
    q = (sa.select(t).where(t.c.fuente == "copycoders", t.c.firma.isnot(None), t.c.firma != "")
         .order_by(t.c.id).limit(limite * 4))
    with db.conectar() as con:
        filas = [_a_dict(r) for r in con.execute(q)]
    return [r for r in filas if not (r.get("extra") or {}).get("traducida")][:limite]


def marcar_traducidas(pares):
    t = db.referente
    n = 0
    with db.conectar() as con:
        for rid, firma in pares:
            firma = _texto(firma)
            if not firma:
                continue
            f = con.execute(sa.select(t.c.extra).where(t.c.id == rid)).first()
            if not f:
                continue
            extra = dict(f.extra or {})
            extra["traducida"] = True
            n += con.execute(t.update().where(t.c.id == rid)
                             .values(firma=firma, extra=extra, actualizado_en=db.ahora())).rowcount
    return n


# ---------------------------------------------------------------- barridos ---

def crear_barrido(cliente, fuente, consulta, tope, pedido_por=None, usd_estimado=0.0):
    if fuente not in FUENTES:
        raise ErrorDatos(f"Fuente desconocida: {fuente}")
    ahora = db.ahora()
    with db.conectar() as con:
        return con.execute(db.barrido.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, fuente=fuente, consulta=dict(consulta or {}),
            tope=int(tope or 0), estado="en_cola", traidos=0, nuevos=0, clasificados=0, pendientes=0, con_imagen=0,
            usd_estimado=float(usd_estimado or 0.0), usd_real=0.0, llamadas_fuente=0,
            pedido_por=_texto(pedido_por, 40) or None, extra={})).inserted_primary_key[0]


def actualizar_barrido(barrido_id, **campos):
    malos = set(campos) - set(_BARRIDO_COLS)
    if malos:
        raise ErrorDatos(f"Campos no editables: {', '.join(sorted(malos))}")
    if "estado" in campos and campos["estado"] not in ESTADOS_BARRIDO:
        raise ErrorDatos(f"Estado de barrido inválido: {campos['estado']}")
    t = db.barrido
    with db.conectar() as con:
        return con.execute(t.update().where(t.c.id == barrido_id)
                           .values(actualizado_en=db.ahora(), **campos)).rowcount == 1


def barrido(barrido_id):
    t = db.barrido
    with db.conectar() as con:
        f = con.execute(sa.select(t).where(t.c.id == barrido_id)).first()
        return _a_dict(f) if f else None


def barridos(cliente=None, fuente=None):
    t = db.barrido
    q = sa.select(t).where(t.c.cliente.is_(None) if cliente is None else t.c.cliente == cliente)
    if fuente:
        q = q.where(t.c.fuente == fuente)
    with db.conectar() as con:
        return [_a_dict(r) for r in con.execute(q.order_by(t.c.id.desc()))]
