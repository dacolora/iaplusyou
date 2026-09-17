"""
Experimentos del motor (no legado): un experimento agrupa piezas (finales por
país o clones) y se lanza a Meta como 1 campaña → 1 conjunto por país → 1
anuncio por pieza. Este módulo es solo datos (SQLAlchemy Core); las llamadas a
Meta viven en lanzador.py. Campañas (ads.py) sigue usando el experimento legado
"Anuncios sueltos" y no pasa por aquí.
"""
import sqlalchemy as sa

import db

ESTADOS_EXPERIMENTO = ("armando", "lanzando", "pausado", "corriendo", "cerrado", "error",
                       "esperando_aprobacion", "decidido")
ESTADOS_PIEZA = ("en_cola", "publicando", "pausado", "activo", "error")
# Cómo se miden las ventas de un experimento: por el Pixel de Meta (insights),
# por los pedidos de la tienda conectada (utm_content → experimento_pieza) o
# no se miden.
ATRIBUCIONES = ("pixel", "tienda", "ninguna")
_EXP_COLS = ("estado", "error", "meta_campaign_id", "gasto_acumulado", "paises", "nombre", "tope_total",
             "dias", "destino_url", "edad_min", "edad_max", "extra", "modo", "reglas", "atribucion", "objetivo_meta")
_EP_COLS = ("estado", "error", "meta_adset_id", "meta_ad_id", "meta_creative_id", "estado_meta",
            "presupuesto_dia_actual", "extra", "veredicto", "veredicto_motivo", "veredicto_en", "escalon_rescate")
_SNAP_COLS = ("impresiones", "alcance", "frecuencia", "clics", "clics_enlace", "ctr", "cpc", "cpm", "thruplay",
              "thruplay_rate", "gasto", "compras", "ingresos", "roas", "cpa", "fuente_ventas")
_SNAP_INT = {"impresiones", "alcance", "clics", "clics_enlace", "thruplay", "compras"}
_TIPOS_CLON = ("video", "clon_limpio")


def _pais_nuevo(p):
    return {"pais": p["pais"], "idioma": p.get("idioma") or "es",
            "presupuesto_dia": float(p.get("presupuesto_dia") or 0), "meta_adset_id": None, "estado": "en_cola"}


def atribucion_sugerida(cliente):
    """Con qué medir ventas, según lo que el proyecto tiene conectado:
    `pixel` si el Pixel de Meta está disparando (meta_conexion.estado_pixel
    == ok), si no `tienda` si hay una Shopify/Woo conectada (son las que
    exponen pedidos con utm), si no `ninguna`. El Pixel se mira solo en
    caché (`solo_cache=True`): esto corre dentro del POST de crear
    experimento y no puede esperar una ida a Graph; si nadie consultó el
    Pixel hace poco (el botón «Comprobar Pixel» de Configuración es el único
    que lo hace), se sugiere tienda/ninguna.
    Imports tardíos: este módulo es solo datos y meta_conexion/tiendas
    arrastran requests, cifrado, etc."""
    import meta_conexion  # noqa: PLC0415
    import tiendas  # noqa: PLC0415
    if (meta_conexion.estado_pixel(cliente, solo_cache=True) or {}).get("estado") == "ok":
        return "pixel"
    if any(t["tipo"] in ("shopify", "woo") and t["estado"] == "conectada" for t in tiendas.listar(cliente)):
        return "tienda"
    return "ninguna"


def crear(cliente, nombre, paises, objetivo_meta, dias, tope_total, destino_url, moneda,
          edad_min=18, edad_max=65, modo="manual", atribucion=None):
    """`atribucion` None → la sugerida para el proyecto (atribucion_sugerida);
    un valor fuera de ATRIBUCIONES es ValueError."""
    if atribucion is None:
        atribucion = atribucion_sugerida(cliente)
    if atribucion not in ATRIBUCIONES:
        raise ValueError(f"Atribución no válida: {atribucion!r} (usa pixel, tienda o ninguna).")
    ahora = db.ahora()
    with db.conectar() as con:
        return con.execute(db.experimento.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, nombre=nombre, modo=modo, reglas={},
            paises=[_pais_nuevo(p) for p in paises], moneda=moneda, tope_total=float(tope_total), dias=int(dias),
            objetivo_meta=objetivo_meta, atribucion=atribucion, estado="armando", gasto_acumulado=0.0,
            legado=False, destino_url=destino_url, edad_min=int(edad_min), edad_max=int(edad_max),
            extra={})).inserted_primary_key[0]


def _bloquear(con, tabla, fila_id, cliente):
    """Toma el lock de escritura de SQLite ANTES de leer (semántica de
    `BEGIN IMMEDIATE`). pysqlite (modo legacy) solo emite `BEGIN` delante de
    un INSERT/UPDATE/DELETE: un SELECT seguido de UPDATE deja el SELECT en
    autocommit y dos procesos (gunicorn + worker) leen la misma foto y el
    último en escribir pisa al otro (lost update, comprobado con dos hilos).
    Un UPDATE sin efecto sobre la fila objetivo obliga al driver a abrir la
    transacción y tomar el lock RESERVED ya; con `busy_timeout=5000` el
    segundo escritor espera en vez de fallar, así que el SELECT que sigue ve
    lo que dejó el anterior. Devuelve True si la fila existe."""
    r = con.execute(tabla.update().where(tabla.c.id == fila_id, tabla.c.cliente == cliente)
                    .values(actualizado_en=tabla.c.actualizado_en))
    return r.rowcount == 1


def _hijo_existente(con, cliente, padre_id, pieza_origen_ep_id):
    e = db.experimento
    return con.execute(sa.select(e.c.id).where(
        e.c.cliente == cliente, e.c.legado.is_(False),
        e.c.extra["padre_experimento_id"].as_integer() == padre_id,
        e.c.extra["origen_ep_id"].as_integer() == pieza_origen_ep_id).order_by(e.c.id)).scalar()


def crear_hijo(cliente, padre_id, nombre, pieza_origen_ep_id):
    """Experimento derivado (Bloque 4): copia países (con presupuestos, sin
    conjuntos de Meta), moneda, días, objetivo, destino, edades, modo y
    reglas del padre; nace `armando` sin piezas. `extra` guarda el vínculo
    (padre_experimento_id, origen_ep_id) y la `profundidad` (la del padre +
    1: el decisor deja de derivar solo a partir de 2). El tope del hijo es lo
    que le queda al padre (`tope_total - gasto_acumulado`, mínimo 0): el
    tope acota a toda la familia, no a cada generación. Idempotente: si ya
    hay un hijo de este padre para esa pieza, devuelve ese id (el lock lo
    toma sobre la fila del padre, así dos `planificar` a la vez no crean
    dos hijos). ValueError si el padre no existe."""
    ahora = db.ahora()
    with db.conectar() as con:
        if not _bloquear(con, db.experimento, padre_id, cliente):
            raise ValueError("Ese experimento no existe.")
        existente = _hijo_existente(con, cliente, padre_id, pieza_origen_ep_id)
        if existente:
            return existente
        f = _fila_experimento(con, cliente, padre_id)
        if not f:
            raise ValueError("Ese experimento no existe.")
        m = f._mapping
        e = db.experimento
        extra_padre = m[e.c.extra] or {}
        tope = max(0.0, float(m[e.c.tope_total] or 0) - float(m[e.c.gasto_acumulado] or 0))
        return con.execute(e.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, nombre=nombre, modo=m[e.c.modo],
            producto_id=m[e.c.producto_id], reglas=dict(m[e.c.reglas] or {}),
            paises=[_pais_nuevo(p) for p in (m[e.c.paises] or [])],
            moneda=m[e.c.moneda], tope_total=tope, dias=m[e.c.dias],
            objetivo_meta=m[e.c.objetivo_meta], atribucion=m[e.c.atribucion] or "ninguna", estado="armando",
            gasto_acumulado=0.0, legado=False, destino_url=m[e.c.destino_url], edad_min=m[e.c.edad_min],
            edad_max=m[e.c.edad_max],
            extra={"padre_experimento_id": padre_id, "origen_ep_id": pieza_origen_ep_id,
                   "profundidad": int(extra_padre.get("profundidad") or 0) + 1})).inserted_primary_key[0]


def profundidad(ex):
    """Generaciones de derivación por encima de este experimento (0 = raíz)."""
    return int(((ex or {}).get("extra") or {}).get("profundidad") or 0)


def _fila_experimento(con, cliente, experimento_id):
    return con.execute(sa.select(db.experimento).where(
        db.experimento.c.id == experimento_id, db.experimento.c.cliente == cliente,
        db.experimento.c.legado.is_(False))).first()


def actualizar(cliente, experimento_id, **campos):
    malos = set(campos) - set(_EXP_COLS)
    if malos:
        raise ValueError(f"Campos no permitidos: {sorted(malos)}")
    with db.conectar() as con:
        con.execute(db.experimento.update().where(
            db.experimento.c.id == experimento_id, db.experimento.c.cliente == cliente,
            db.experimento.c.legado.is_(False)).values(actualizado_en=db.ahora(), **campos))


def actualizar_extra(cliente, experimento_id, fn, **campos):
    """Read-modify-write atómico de `experimento.extra`: toma el lock de
    escritura (`_bloquear`, semántica BEGIN IMMEDIATE), SELECT del `extra`
    actual y UPDATE con `fn(extra) -> extra`, todo en UNA transacción. Dos
    llamadas concurrentes (hilos de gunicorn o el worker) se ejecutan una
    detrás de otra, cada una sobre el `extra` que dejó la anterior: no hay
    lost update aunque el llamador tenga una foto vieja del experimento.
    `campos` son otras columnas a escribir en el mismo UPDATE (p. ej.
    `estado`). Todo lo que modifique `extra` (derivaciones, `activado_en`
    del lanzador) debe pasar por acá y nunca por `actualizar(extra=...)`,
    que reemplaza el dict con lo que el llamador leyó. Devuelve el `extra`
    escrito (None si no existe)."""
    malos = (set(campos) - set(_EXP_COLS)) | ({"extra"} & set(campos))
    if malos:
        raise ValueError(f"Campos no permitidos: {sorted(malos)}")
    with db.conectar() as con:
        if not _bloquear(con, db.experimento, experimento_id, cliente):
            return None
        f = _fila_experimento(con, cliente, experimento_id)
        if not f:
            return None
        extra = fn(dict(f._mapping[db.experimento.c.extra] or {}))
        con.execute(db.experimento.update().where(db.experimento.c.id == experimento_id)
                    .values(actualizado_en=db.ahora(), extra=extra, **campos))
        return extra


def actualizar_pais(cliente, experimento_id, pais, **campos):
    """RMW de `paises` con el mismo lock previo que actualizar_extra."""
    with db.conectar() as con:
        if not _bloquear(con, db.experimento, experimento_id, cliente):
            return
        f = _fila_experimento(con, cliente, experimento_id)
        if not f:
            return
        paises = [dict(p) for p in (f._mapping[db.experimento.c.paises] or [])]
        for p in paises:
            if p["pais"] == pais:
                p.update(campos)
        con.execute(db.experimento.update().where(db.experimento.c.id == experimento_id)
                    .values(paises=paises, actualizado_en=db.ahora()))


def agregar_pieza(cliente, experimento_id, pieza_id, pais):
    """None si el experimento no existe/no es de ese cliente/es legado, o si la
    pieza no es de ese cliente (M8) — la validación de negocio (país válido,
    estado del experimento, etc.) sigue viviendo en dashboard._agregar_pieza_validada;
    esto es solo el guard de tenencia que agregar_pieza necesita para ser
    seguro si algún otro llamador la usa sin pasar por ahí."""
    with db.conectar() as con:
        # Lock antes del SELECT de dedupe: dos pasadas de `avanzar` a la vez
        # no insertan la misma pieza dos veces.
        if not _bloquear(con, db.experimento, experimento_id, cliente):
            return None
        if not _fila_experimento(con, cliente, experimento_id):
            return None
        pieza_ok = con.execute(sa.select(db.pieza.c.id).where(
            db.pieza.c.id == pieza_id, db.pieza.c.cliente == cliente)).scalar()
        if not pieza_ok:
            return None
        existente = con.execute(sa.select(db.experimento_pieza.c.id).where(
            db.experimento_pieza.c.experimento_id == experimento_id, db.experimento_pieza.c.pieza_id == pieza_id,
            db.experimento_pieza.c.pais == pais, db.experimento_pieza.c.cliente == cliente)).scalar()
        if existente:
            return existente
        ahora = db.ahora()
        return con.execute(db.experimento_pieza.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, experimento_id=experimento_id,
            pieza_id=pieza_id, pais=pais, estado="en_cola", veredicto="pendiente", escalon_rescate=0,
            extra={})).inserted_primary_key[0]


def experimento_de_pieza(cliente, ep_id):
    """Id del experimento dueño de una pieza, o None si no existe (para
    ese cliente). Usado por lanzador._experimento_de_pieza en vez de que
    ese módulo consulte experimento_pieza con SQL crudo."""
    with db.conectar() as con:
        return con.execute(sa.select(db.experimento_pieza.c.experimento_id).where(
            db.experimento_pieza.c.id == ep_id, db.experimento_pieza.c.cliente == cliente)).scalar()


def quitar_pieza(cliente, experimento_id, ep_id):
    with db.conectar() as con:
        f = con.execute(sa.select(db.experimento_pieza).where(
            db.experimento_pieza.c.id == ep_id, db.experimento_pieza.c.cliente == cliente,
            db.experimento_pieza.c.experimento_id == experimento_id)).first()
        if not f or f._mapping[db.experimento_pieza.c.estado] != "en_cola" or f._mapping[db.experimento_pieza.c.meta_ad_id]:
            return False
        con.execute(db.metrica_snapshot.delete().where(db.metrica_snapshot.c.experimento_pieza_id == ep_id))
        con.execute(db.experimento_pieza.delete().where(db.experimento_pieza.c.id == ep_id))
        return True


def actualizar_pieza(cliente, ep_id, **campos):
    malos = set(campos) - set(_EP_COLS)
    if malos:
        raise ValueError(f"Campos no permitidos: {sorted(malos)}")
    with db.conectar() as con:
        con.execute(db.experimento_pieza.update().where(
            db.experimento_pieza.c.id == ep_id, db.experimento_pieza.c.cliente == cliente)
            .values(actualizado_en=db.ahora(), **campos))


def marcar_pieza(cliente, ep_id, **flags):
    """Read-modify-write atómico de `extra` para las banderas de idempotencia
    del decisor (derivado, rescatado_en_escalon, archivado): relee `extra`
    dentro de la misma transacción, justo antes de escribir, así no pisa lo
    que otra parte del motor (p. ej. lanzador.activar_pieza, o Task 5) haya
    escrito en `extra` entre que acciones.ejecutar leyó la pieza y este
    marcado. El lock se toma antes del SELECT (`_bloquear`, ver ahí por
    qué); sin eso el SELECT corría en autocommit y dos marcados a la vez se
    pisaban. ValueError si la pieza no existe."""
    ep = db.experimento_pieza
    with db.conectar() as con:
        if not _bloquear(con, ep, ep_id, cliente):
            raise ValueError("Esa pieza no está en el experimento.")
        f = con.execute(sa.select(ep.c.extra).where(
            ep.c.id == ep_id, ep.c.cliente == cliente)).first()
        if f is None:
            raise ValueError("Esa pieza no está en el experimento.")
        extra = {**(f._mapping[ep.c.extra] or {}), **flags}
        con.execute(ep.update().where(ep.c.id == ep_id, ep.c.cliente == cliente)
                    .values(actualizado_en=db.ahora(), extra=extra))


def _snapshot_a_dict(f):
    m = f._mapping
    out = {c: m[db.metrica_snapshot.c[c]] for c in _SNAP_COLS}
    out.update(m[db.metrica_snapshot.c.extra] or {})
    out["tomado_en"] = m[db.metrica_snapshot.c.tomado_en]
    return out


def _ultima_metrica(con, ep_id):
    f = con.execute(sa.select(db.metrica_snapshot).where(db.metrica_snapshot.c.experimento_pieza_id == ep_id)
                    .order_by(db.metrica_snapshot.c.id.desc()).limit(1)).first()
    return _snapshot_a_dict(f) if f else {}


def ultima_metrica(ep_id):
    with db.conectar() as con:
        return _ultima_metrica(con, ep_id)


def snapshots(ep_id):
    """Todas las métricas de una pieza en orden cronológico (misma forma que
    ultima_metrica, incluido tomado_en). Es lo que consume decisor.decidir."""
    with db.conectar() as con:
        filas = con.execute(sa.select(db.metrica_snapshot).where(db.metrica_snapshot.c.experimento_pieza_id == ep_id)
                            .order_by(db.metrica_snapshot.c.id))
        return [_snapshot_a_dict(f) for f in filas]


def snapshot(ep_id, metricas, tomado_en=None):
    """Guarda una foto ACUMULADA de las métricas de una pieza. `tomado_en`
    (ISO naive, como db.ahora()) solo lo fijan los tests y un backfill: en
    producción siempre es «ahora»."""
    valores, extra = {}, {}
    for k, v in (metricas or {}).items():
        if k in _SNAP_COLS:
            if k == "fuente_ventas":
                valores[k] = v or "ninguna"
            else:
                valores[k] = int(float(v or 0)) if k in _SNAP_INT else float(v or 0)
        else:
            extra[k] = v
    with db.conectar() as con:
        return con.execute(db.metrica_snapshot.insert().values(
            experimento_pieza_id=ep_id, tomado_en=tomado_en or db.ahora(), extra=extra,
            **valores)).inserted_primary_key[0]


def _piezas(con, cliente, experimento_id):
    ep, pz, cp = db.experimento_pieza, db.pieza, db.concepto
    q = (sa.select(ep, pz.c.tipo, pz.c.idioma.label("p_idioma"), pz.c.url_video, pz.c.url_miniatura, pz.c.legado_id.label("p_legado"),
                   pz.c.pais.label("p_pais"), pz.c.duracion_s, cp.c.extra.label("c_extra"))
         .select_from(ep.outerjoin(pz, pz.c.id == ep.c.pieza_id).outerjoin(cp, cp.c.id == pz.c.concepto_id))
         .where(ep.c.experimento_id == experimento_id, ep.c.cliente == cliente).order_by(ep.c.id))
    out = []
    for f in con.execute(q):
        m = f._mapping
        tipo = "final" if m["tipo"] == "final" else "clon"
        nombre = (f"Final {m['p_idioma']}_{m['p_pais']}" if tipo == "final"
                  else ((m["c_extra"] or {}).get("accion_central") or m["p_legado"] or f"Pieza {m[ep.c.pieza_id]}"))
        out.append({
            "id": m[ep.c.id], "pieza_id": m[ep.c.pieza_id], "pais": m[ep.c.pais], "estado": m[ep.c.estado],
            "error": m[ep.c.error], "meta_adset_id": m[ep.c.meta_adset_id], "meta_ad_id": m[ep.c.meta_ad_id],
            "meta_creative_id": m[ep.c.meta_creative_id], "estado_meta": m[ep.c.estado_meta],
            "presupuesto_dia_actual": m[ep.c.presupuesto_dia_actual], "veredicto": m[ep.c.veredicto],
            "veredicto_motivo": m[ep.c.veredicto_motivo], "veredicto_en": m[ep.c.veredicto_en],
            "nombre": nombre[:80], "url_video": m["url_video"], "url_miniatura": m["url_miniatura"], "tipo": tipo,
            "idioma": m["p_idioma"], "legado_id": m["p_legado"], "duracion_s": m["duracion_s"],
            "metricas": _ultima_metrica(con, m[ep.c.id]), "creado_en": m[ep.c.creado_en],
            "extra": m[ep.c.extra] or {}, "escalon_rescate": m[ep.c.escalon_rescate] or 0,
        })
    return out


def piezas(cliente, experimento_id):
    with db.conectar() as con:
        return _piezas(con, cliente, experimento_id)


def _resumen(piezas_):
    con_m = [p["metricas"] for p in piezas_ if p["metricas"]]
    cpcs = [m["cpc"] for m in con_m if (m.get("cpc") or 0) > 0]
    ctrs = [m["ctr"] for m in con_m if (m.get("ctr") or 0) > 0]
    return {"gasto": round(sum(float(m.get("gasto") or 0) for m in con_m), 2),
            "mejor_cpc": min(cpcs) if cpcs else None, "mejor_ctr": max(ctrs) if ctrs else None,
            "activos": sum(1 for p in piezas_ if p["estado"] == "activo"), "total": len(piezas_)}


def _eventos(con, cliente, experimento_id, limite):
    q = (sa.select(db.evento).where(db.evento.c.experimento_id == experimento_id, db.evento.c.cliente == cliente)
         .order_by(db.evento.c.id.desc()))
    if limite:
        q = q.limit(limite)
    return [{"id": f._mapping[db.evento.c.id], "tipo": f._mapping[db.evento.c.tipo], "mensaje": f._mapping[db.evento.c.mensaje],
             "datos": f._mapping[db.evento.c.datos] or {}, "ep_id": f._mapping[db.evento.c.experimento_pieza_id],
             "creado_en": f._mapping[db.evento.c.creado_en]} for f in con.execute(q)]


def _hijos(con, cliente, experimento_id):
    """Ids (ascendentes) de los experimentos cuyo extra.padre_experimento_id es este."""
    e = db.experimento
    return [f._mapping[e.c.id] for f in con.execute(
        sa.select(e.c.id).where(e.c.cliente == cliente, e.c.legado.is_(False),
                                e.c.extra["padre_experimento_id"].as_integer() == experimento_id)
        .order_by(e.c.id))]


def _propuestas_pendientes(con, cliente, experimento_id):
    p = db.propuesta
    return con.execute(sa.select(sa.func.count()).select_from(p).where(
        p.c.cliente == cliente, p.c.experimento_id == experimento_id, p.c.estado == "pendiente")).scalar() or 0


def _a_dict(con, f, limite_eventos):
    m = f._mapping
    e = db.experimento
    pzs = _piezas(con, m[e.c.cliente], m[e.c.id])
    extra = m[e.c.extra] or {}
    return {
        "id": m[e.c.id], "nombre": m[e.c.nombre], "estado": m[e.c.estado], "modo": m[e.c.modo],
        "paises": [dict(p) for p in (m[e.c.paises] or [])], "moneda": m[e.c.moneda], "tope_total": m[e.c.tope_total],
        "dias": m[e.c.dias], "objetivo_meta": m[e.c.objetivo_meta], "destino_url": m[e.c.destino_url],
        "edad_min": m[e.c.edad_min], "edad_max": m[e.c.edad_max], "meta_campaign_id": m[e.c.meta_campaign_id],
        "gasto_acumulado": m[e.c.gasto_acumulado] or 0.0, "error": m[e.c.error], "extra": extra,
        "reglas": m[e.c.reglas] or {}, "atribucion": m[e.c.atribucion] or "ninguna", "creado_en": m[e.c.creado_en],
        "piezas": pzs, "resumen": _resumen(pzs),
        "eventos": _eventos(con, m[e.c.cliente], m[e.c.id], limite_eventos),
        "padre_experimento_id": extra.get("padre_experimento_id"),
        "hijos": _hijos(con, m[e.c.cliente], m[e.c.id]),
        "propuestas_pendientes": _propuestas_pendientes(con, m[e.c.cliente], m[e.c.id]),
    }


def cargar(cliente):
    with db.conectar() as con:
        filas = con.execute(sa.select(db.experimento).where(
            db.experimento.c.cliente == cliente, db.experimento.c.legado.is_(False))
            .order_by(db.experimento.c.id.desc()))
        return [_a_dict(con, f, 30) for f in filas]


def obtener(cliente, experimento_id):
    with db.conectar() as con:
        f = _fila_experimento(con, cliente, experimento_id)
        return _a_dict(con, f, None) if f else None


def registrar_evento(cliente, experimento_id, tipo, mensaje, datos=None, ep_id=None):
    with db.conectar() as con:
        return con.execute(db.evento.insert().values(
            cliente=cliente, experimento_id=experimento_id, experimento_pieza_id=ep_id, tipo=tipo,
            mensaje=mensaje, datos=datos or {}, creado_en=db.ahora())).inserted_primary_key[0]


def eventos(cliente, experimento_id, limite=None):
    with db.conectar() as con:
        return _eventos(con, cliente, experimento_id, limite)


def elegibles(cliente):
    """Finales listas/degradadas (para su país) y clones de video listos (para
    cualquier país). Imágenes y piezas sin url_video no entran."""
    pz, cp = db.pieza, db.concepto
    q = (sa.select(pz, cp.c.extra.label("c_extra"))
         .select_from(pz.outerjoin(cp, cp.c.id == pz.c.concepto_id))
         .where(pz.c.cliente == cliente, pz.c.url_video.isnot(None),
                cp.c.archivado.isnot(True),
                sa.or_(sa.and_(pz.c.tipo == "final", pz.c.estado.in_(("listo", "degradada"))),
                       sa.and_(pz.c.tipo.in_(_TIPOS_CLON), pz.c.estado == "listo")))
         .order_by(pz.c.id.desc()))
    out = []
    with db.conectar() as con:
        for f in con.execute(q):
            m = f._mapping
            tipo = "final" if m[pz.c.tipo] == "final" else "clon"
            nombre = (f"Final {m[pz.c.idioma]}_{m[pz.c.pais]} · {m[pz.c.legado_id] or ''}" if tipo == "final"
                      else ((m["c_extra"] or {}).get("accion_central") or m[pz.c.legado_id] or f"Pieza {m[pz.c.id]}"))
            out.append({"pieza_id": m[pz.c.id], "legado_id": m[pz.c.legado_id], "tipo": tipo, "nombre": nombre[:80],
                        "url_video": m[pz.c.url_video], "url_miniatura": m[pz.c.url_miniatura],
                        "idioma": m[pz.c.idioma], "pais": m[pz.c.pais] if tipo == "final" else None,
                        "duracion_s": m[pz.c.duracion_s]})
    return out
