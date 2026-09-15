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


def guardar_guion_base(cliente, cf_id, guion):
    """Guarda el guion base (capa 0 de Final Edition) en `concepto.guion_base`.
    Devuelve False si la sesión no existe."""
    with db.conectar() as con:
        f = _ids(con, cliente, cf_id)
        if not f:
            return False
        con.execute(db.concepto.update().where(db.concepto.c.id == f[0])
                    .values(actualizado_en=db.ahora(), guion_base=guion))
    return True


def guion_base(cliente, cf_id):
    """Guion base guardado para la sesión, o None si no hay o no existe."""
    with db.conectar() as con:
        f = _ids(con, cliente, cf_id)
        if not f:
            return None
        return con.execute(sa.select(db.concepto.c.guion_base)
                           .where(db.concepto.c.id == f[0])).scalar()


def eliminar(cliente, cf_id):
    with db.conectar() as con:
        f = _ids(con, cliente, cf_id)
        if not f:
            return False
        cid, pid = f[0], f[1]
        # Las piezas finales cuelgan de la clon (FK padre_pieza_id): van primero.
        con.execute(db.pieza.delete().where(db.pieza.c.padre_pieza_id == pid, db.pieza.c.tipo == "final"))
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


# ------------------------------------------------------------ piezas finales ---
# Una pieza `final` cuelga de la pieza clon de la sesión (padre_pieza_id) y
# comparte su concepto. `cargar`/`_ids` las excluyen (tipo != "final") para
# que Crear siga viendo una sola pieza por sesión.

_FINAL_COLS = ("estado", "url_video", "url_miniatura", "url_local", "duracion_s",
               "capas", "costo_usd", "guion", "error")


def _final_a_dict(p):
    return {
        "id": p.legado_id, "idioma": p.idioma, "pais": p.pais, "estado": p.estado,
        "video_url": p.url_video, "url_miniatura": p.url_miniatura, "url_local": p.url_local,
        "duracion_s": p.duracion_s, "costo_usd": p.costo_usd, "capas": p.capas or {},
        "guion": p.guion, "error": p.error, "creado_en": p.creado_en,
    }


def _fila_final(con, cliente, final_id):
    return con.execute(sa.select(db.pieza).where(
        db.pieza.c.cliente == cliente, db.pieza.c.tipo == "final",
        db.pieza.c.legado_id == final_id)).first()


def crear_final(cliente, cf_id, idioma, pais):
    """Crea (o reinicia a `generando`) la pieza final de la sesión para ese
    idioma/país. Devuelve su legado_id `<cf_id>__<idioma>_<pais>`.

    Si ya existía (se está reproduciendo un destino que ya tenía una final),
    NO se borra `url_video`/`url_miniatura`: la cuadrícula sigue mostrando el
    video anterior mientras el worker produce el nuevo, y solo se pierde si
    el nuevo intento tiene éxito (`actualizar_final` con estado "listo" o
    "degradada" los sobrescribe) — si falla, `actualizar_final` con
    estado="error" los deja intactos, así que el cliente nunca se queda sin
    nada por un reintento fallido (I4)."""
    final_id = f"{cf_id}__{idioma}_{pais}"
    with db.conectar() as con:
        f = _ids(con, cliente, cf_id)
        if not f:
            raise ValueError(f"No existe la sesión {cf_id} de {cliente}.")
        cid, pid = f[0], f[1]
        ahora = db.ahora()
        existente = _fila_final(con, cliente, final_id)
        if existente:
            con.execute(db.pieza.update().where(db.pieza.c.id == existente._mapping[db.pieza.c.id]).values(
                actualizado_en=ahora, estado="generando", error=None, capas={}, costo_usd=None))
        else:
            con.execute(db.pieza.insert().values(
                cliente=cliente, creado_en=ahora, actualizado_en=ahora, concepto_id=cid, tipo="final",
                idioma=idioma, pais=pais, estado="generando", padre_pieza_id=pid, legado_id=final_id,
                capas={}, extra={}))
    return final_id


def actualizar_final(cliente, final_id, **campos):
    """Actualiza columnas de la pieza final (estado, url_video, url_miniatura,
    url_local, duracion_s, capas, costo_usd, guion, error). False si no existe."""
    desconocidos = set(campos) - set(_FINAL_COLS)
    if desconocidos:
        raise ValueError(f"actualizar_final: campos no permitidos {sorted(desconocidos)}")
    with db.conectar() as con:
        fila = _fila_final(con, cliente, final_id)
        if not fila:
            return False
        con.execute(db.pieza.update().where(db.pieza.c.id == fila._mapping[db.pieza.c.id])
                    .values(actualizado_en=db.ahora(), **campos))
    return True


def finales(cliente, cf_id):
    """Piezas finales de la sesión (dicts con id=legado_id, idioma, pais,
    estado, video_url, url_miniatura, url_local, duracion_s, costo_usd, capas,
    guion, error, creado_en), en orden de creación."""
    with db.conectar() as con:
        f = _ids(con, cliente, cf_id)
        if not f:
            return []
        filas = con.execute(sa.select(db.pieza).where(
            db.pieza.c.tipo == "final", db.pieza.c.padre_pieza_id == f[1]).order_by(db.pieza.c.id)).fetchall()
    return [_final_a_dict(_Cols(fila, db.pieza)) for fila in filas]


def final_por_legado(cliente, final_id):
    """Una pieza final por su legado_id, o None."""
    with db.conectar() as con:
        fila = _fila_final(con, cliente, final_id)
    return _final_a_dict(_Cols(fila, db.pieza)) if fila else None


def eliminar_final(cliente, final_id):
    with db.conectar() as con:
        fila = _fila_final(con, cliente, final_id)
        if not fila:
            return False
        con.execute(db.pieza.delete().where(db.pieza.c.id == fila._mapping[db.pieza.c.id]))
    return True


def pieza_id_por_legado(cliente, legado_id):
    """Id numérico de la fila `pieza` (clon o final) a partir de su id legado
    (cf_... o cf_...__idioma_pais). Lo usa Experimentos para enlazar piezas."""
    with db.conectar() as con:
        return con.execute(sa.select(db.pieza.c.id).where(
            db.pieza.c.cliente == cliente, db.pieza.c.legado_id == legado_id)).scalar()
