"""
Tiendas conectadas (Shopify/Woo/MELI/CSV/URL), su catálogo normalizado
(`producto`) y sus pedidos (`pedido`) — bloque 5 del motor de ecommerce.
Solo datos (SQLAlchemy Core), siguiendo el estilo de experimentos.py:
`db.conectar()` por operación, todo filtrado por `cliente`, acceso vía
`_mapping`. Las credenciales de cada tienda se guardan cifradas (cifrado.py)
y nunca salen de `credenciales()` — `listar`/`obtener` las omiten a propósito.

A diferencia de experimento/experimento_pieza (Bloque 3/4, donde gunicorn y
el worker escriben la misma fila a la vez), acá solo el worker sincroniza
tiendas/productos/pedidos (`tareas/` de los conectores) — el dashboard solo
lee y marca banderas puntuales (`marcar_producto`, `actualizar`). No hay
carrera de lost-update que justifique el lock `_bloquear` de experimentos.py.
"""
import json

import sqlalchemy as sa

import cifrado
import db

_TIENDA_CAMPOS = ("id", "tipo", "nombre", "dominio", "estado", "error",
                   "ultima_sync_productos", "ultima_sync_pedidos", "creado_en")
_TIENDA_CAMPOS_EDITABLES = ("estado", "error", "ultima_sync_productos", "ultima_sync_pedidos", "nombre", "dominio")

_PRODUCTO_CAMPOS_DATOS = ("nombre", "descripcion", "precio", "moneda", "url_compra", "fotos", "categoria",
                          "url_imagen_principal", "extra")
_PRODUCTO_CAMPOS_TODOS = ("id", "cliente", "creado_en", "actualizado_en", "fuente", "fuente_id",
                          "nombre", "descripcion", "precio", "moneda", "url_compra", "fotos", "categoria",
                          "activo_catalogo_id", "prioridad", "en_prueba", "archivado",
                          "url_imagen_principal", "extra")
_PRODUCTO_CAMPOS_MARCA = ("en_prueba", "prioridad", "archivado", "activo_catalogo_id", "url_compra",
                          "precio", "moneda")


# --- tiendas ---------------------------------------------------------------

def _tienda_a_dict(fila):
    m = fila._mapping
    t = db.tienda
    return {c: m[t.c[c]] for c in _TIENDA_CAMPOS}


def conectar(cliente, tipo, credenciales, nombre=None, dominio=None):
    """Una tienda por (cliente, tipo): si ya existe, reemplaza sus
    credenciales (y su nombre/dominio si se pasan) en vez de duplicarla."""
    ahora = db.ahora()
    token = cifrado.cifrar(json.dumps(credenciales))
    t = db.tienda
    with db.conectar() as con:
        fila = con.execute(sa.select(t.c.id).where(t.c.cliente == cliente, t.c.tipo == tipo)).first()
        if fila:
            tid = fila[0]
            valores = {"actualizado_en": ahora, "credenciales": token, "estado": "conectada", "error": None}
            if nombre is not None:
                valores["nombre"] = nombre
            if dominio is not None:
                valores["dominio"] = dominio
            con.execute(t.update().where(t.c.id == tid).values(**valores))
            return tid
        return con.execute(t.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, tipo=tipo, credenciales=token,
            nombre=nombre, dominio=dominio, estado="conectada", error=None)).inserted_primary_key[0]


def credenciales(cliente, tienda_id):
    """dict de credenciales descifradas, o None si la tienda no existe (o no
    es de ese cliente). Deja pasar cifrado.ErrorCifrado si FLASK_SECRET_KEY
    cambió desde que se guardaron — el llamador decide cómo avisarlo."""
    t = db.tienda
    with db.conectar() as con:
        fila = con.execute(sa.select(t.c.credenciales).where(t.c.id == tienda_id, t.c.cliente == cliente)).first()
    if not fila or not fila[0]:
        return None
    return json.loads(cifrado.descifrar(fila[0]))


def listar(cliente):
    t = db.tienda
    with db.conectar() as con:
        filas = con.execute(sa.select(t).where(t.c.cliente == cliente).order_by(t.c.id))
        return [_tienda_a_dict(f) for f in filas]


def obtener(cliente, tienda_id):
    t = db.tienda
    with db.conectar() as con:
        fila = con.execute(sa.select(t).where(t.c.id == tienda_id, t.c.cliente == cliente)).first()
    return _tienda_a_dict(fila) if fila else None


def actualizar(cliente, tienda_id, **campos):
    malos = set(campos) - set(_TIENDA_CAMPOS_EDITABLES)
    if malos:
        raise ValueError(f"Campos no permitidos: {sorted(malos)}")
    t = db.tienda
    with db.conectar() as con:
        con.execute(t.update().where(t.c.id == tienda_id, t.c.cliente == cliente)
                    .values(actualizado_en=db.ahora(), **campos))


def desconectar(cliente, tienda_id):
    """Borra la tienda. Los productos que vinieron de ella no se borran —
    quedan con su `fuente`/`fuente_id` de siempre, solo se archivan (así no
    desaparecen de golpe de un catálogo/experimento que ya los use)."""
    t, p = db.tienda, db.producto
    with db.conectar() as con:
        fila = con.execute(sa.select(t.c.tipo).where(t.c.id == tienda_id, t.c.cliente == cliente)).first()
        if not fila:
            return False
        tipo = fila[0]
        con.execute(t.delete().where(t.c.id == tienda_id, t.c.cliente == cliente))
        con.execute(p.update().where(p.c.cliente == cliente, p.c.fuente == tipo)
                    .values(archivado=True, actualizado_en=db.ahora()))
        return True


# --- productos ---------------------------------------------------------------

def _producto_a_dict(fila):
    m = fila._mapping
    p = db.producto
    return {c: m[p.c[c]] for c in _PRODUCTO_CAMPOS_TODOS}


def upsert_producto(cliente, fuente, fuente_id, datos):
    """Crea o actualiza el producto (cliente, fuente, fuente_id). Solo toca
    las columnas presentes en `datos` — una sync parcial (p. ej. solo precio)
    no borra `fotos`/`descripcion` ya guardadas. `prioridad`, `en_prueba` y
    `activo_catalogo_id` son banderas del catálogo (marcar_producto) y una
    sync nunca las toca; `archivado` sí se fuerza a False en cada sync: si
    el producto reaparece en la fuente, se desarchiva solo."""
    ahora = db.ahora()
    valores = {k: v for k, v in (datos or {}).items() if k in _PRODUCTO_CAMPOS_DATOS}
    p = db.producto
    with db.conectar() as con:
        fila = con.execute(sa.select(p.c.id).where(
            p.c.cliente == cliente, p.c.fuente == fuente, p.c.fuente_id == fuente_id)).first()
        if fila:
            pid = fila[0]
            con.execute(p.update().where(p.c.id == pid)
                        .values(actualizado_en=ahora, archivado=False, **valores))
            return pid
        return con.execute(p.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, fuente=fuente, fuente_id=fuente_id,
            prioridad=0, en_prueba=False, archivado=False, **valores)).inserted_primary_key[0]


def producto(cliente, producto_id):
    p = db.producto
    with db.conectar() as con:
        fila = con.execute(sa.select(p).where(p.c.id == producto_id, p.c.cliente == cliente)).first()
    return _producto_a_dict(fila) if fila else None


def productos(cliente, incluir_archivados=False):
    p = db.producto
    condiciones = [p.c.cliente == cliente]
    if not incluir_archivados:
        condiciones.append(p.c.archivado.is_(False))
    with db.conectar() as con:
        filas = con.execute(sa.select(p).where(*condiciones).order_by(p.c.prioridad.desc(), p.c.nombre))
        return [_producto_a_dict(f) for f in filas]


def marcar_producto(cliente, producto_id, **campos):
    malos = set(campos) - set(_PRODUCTO_CAMPOS_MARCA)
    if malos:
        raise ValueError(f"Campos no permitidos: {sorted(malos)}")
    p = db.producto
    with db.conectar() as con:
        con.execute(p.update().where(p.c.id == producto_id, p.c.cliente == cliente)
                    .values(actualizado_en=db.ahora(), **campos))


def archivar_faltantes(cliente, fuente, ids_vistos):
    """Archiva los productos de `fuente` que no aparecieron en la última
    sync (su fuente_id no está en `ids_vistos`) y que todavía no lo
    estaban. Devuelve cuántos se archivaron."""
    ids_vistos = set(ids_vistos or [])
    p = db.producto
    condiciones = [p.c.cliente == cliente, p.c.fuente == fuente, p.c.archivado.is_(False)]
    if ids_vistos:
        condiciones.append(p.c.fuente_id.not_in(ids_vistos))
    with db.conectar() as con:
        r = con.execute(p.update().where(*condiciones).values(archivado=True, actualizado_en=db.ahora()))
        return r.rowcount


# --- pedidos -----------------------------------------------------------------

def _pedido_a_dict(fila):
    m = fila._mapping
    pe = db.pedido
    return {"id": m[pe.c.id], "cliente": m[pe.c.cliente], "tienda_id": m[pe.c.tienda_id],
            "fuente_id": m[pe.c.fuente_id], "fecha": m[pe.c.fecha], "total": m[pe.c.total],
            "moneda": m[pe.c.moneda], "items": m[pe.c["items"]] or [], "utm_content": m[pe.c.utm_content],
            "experimento_pieza_id": m[pe.c.experimento_pieza_id]}


def guardar_pedidos(cliente, tienda_id, pedidos):
    """Upsert por (cliente, fuente_id): `INSERT OR IGNORE` primero (así
    `rowcount` cuenta exactamente los pedidos nuevos) y, si ya existía, un
    UPDATE aparte con los datos frescos (el total de un pedido puede seguir
    cambiando — reembolsos parciales, etc. — sin que deje de ser el mismo
    pedido). Nunca toca `experimento_pieza_id`: una resync no debe deshacer
    una atribución ya resuelta. Devuelve cuántos pedidos eran nuevos."""
    pe = db.pedido
    insertados = 0
    with db.conectar() as con:
        for ped in pedidos or []:
            valores = {"fecha": ped["fecha"], "total": ped.get("total"), "moneda": ped.get("moneda"),
                       "items": ped.get("items") or [], "utm_content": ped.get("utm_content")}
            r = con.execute(pe.insert().prefix_with("OR IGNORE").values(
                cliente=cliente, tienda_id=tienda_id, fuente_id=ped["fuente_id"], **valores))
            if r.rowcount:
                insertados += r.rowcount
            else:
                con.execute(pe.update().where(pe.c.cliente == cliente, pe.c.fuente_id == ped["fuente_id"])
                            .values(**valores))
    return insertados


def pedidos_sin_resolver(cliente):
    """Pedidos con `utm_content` (llegaron con una pieza en la URL) que
    todavía no se ligaron a un `experimento_pieza_id` — la cola que debe
    resolver el atribuidor del Bloque 5."""
    pe = db.pedido
    with db.conectar() as con:
        filas = con.execute(sa.select(pe).where(
            pe.c.cliente == cliente, pe.c.utm_content.isnot(None), pe.c.experimento_pieza_id.is_(None))
            .order_by(pe.c.id))
        return [_pedido_a_dict(f) for f in filas]


def resolver_pedido(cliente, pedido_id, ep_id):
    """Liga un pedido a la `experimento_pieza` que lo generó. `False` si la
    pieza no existe o no es de ese cliente (nunca atribuir un pedido a una
    pieza ajena) — la columna sigue siendo FK dura (ver migración 0001), así
    que un `ep_id` inválido también fallaría en el UPDATE, pero esto evita
    ligar cliente A a una pieza real de cliente B."""
    ep = db.experimento_pieza
    pe = db.pedido
    with db.conectar() as con:
        ep_ok = con.execute(sa.select(ep.c.id).where(ep.c.id == ep_id, ep.c.cliente == cliente)).scalar()
        if not ep_ok:
            return False
        con.execute(pe.update().where(pe.c.id == pedido_id, pe.c.cliente == cliente)
                    .values(experimento_pieza_id=ep_id))
        return True


def ventas_por_pieza(cliente, ep_id, desde_iso):
    """Compras e ingresos (suma de `total`) de una pieza desde `desde_iso`
    (comparación lexicográfica — funciona porque `fecha` es ISO de 19
    caracteres, igual que el resto del motor)."""
    pe = db.pedido
    with db.conectar() as con:
        fila = con.execute(sa.select(
            sa.func.count(pe.c.id), sa.func.coalesce(sa.func.sum(pe.c.total), 0.0)
        ).where(pe.c.cliente == cliente, pe.c.experimento_pieza_id == ep_id, pe.c.fecha >= desde_iso)).first()
    return {"compras": int(fila[0] or 0), "ingresos": float(fila[1] or 0.0)}
