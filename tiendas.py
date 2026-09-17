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
from datetime import datetime, timedelta

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
                          "precio", "moneda", "nombre", "descripcion")
# Claves de `producto.extra` que son del motor, no de la fuente: una sync
# reemplaza `extra` con lo que trae el conector (handle, sku, gid…) pero
# estas se conservan. `archivado_por` ("manual" | "sync") distingue un
# «Archivar» de la persona (que la sync NO deshace) de uno por ausencia en la
# tienda (que sí se deshace si reaparece). `vinculo_intentado_en` marca el
# último intento de crear el activo que terminó sin activo, para que el tope
# por corrida del importador atienda primero lo que nunca se intentó.
EXTRA_INTERNO = ("archivado_por", "vinculo_intentado_en")


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
    quedan con su `fuente`/`fuente_id` de siempre, solo se archivan por
    sync (así no desaparecen de golpe de un catálogo/experimento que ya los
    use, y una reconexión los desarchiva sola). Los pedidos tampoco se
    borran: `pedido.tienda_id` es FK a la tienda, así que se desligan
    (`tienda_id=NULL`) en la misma transacción conservando su atribución —
    sin esto el DELETE fallaría con IntegrityError en cuanto la tienda
    tuviera una venta."""
    t, p, pe = db.tienda, db.producto, db.pedido
    ahora = db.ahora()
    with db.conectar() as con:
        fila = con.execute(sa.select(t.c.tipo).where(t.c.id == tienda_id, t.c.cliente == cliente)).first()
        if not fila:
            return False
        tipo = fila[0]
        con.execute(pe.update().where(pe.c.cliente == cliente, pe.c.tienda_id == tienda_id).values(tienda_id=None))
        con.execute(t.delete().where(t.c.id == tienda_id, t.c.cliente == cliente))
        _archivar_en(con, [p.c.cliente == cliente, p.c.fuente == tipo, p.c.archivado.is_(False)], "sync", ahora)
        return True


# --- productos ---------------------------------------------------------------

def _producto_a_dict(fila):
    m = fila._mapping
    p = db.producto
    return {c: m[p.c[c]] for c in _PRODUCTO_CAMPOS_TODOS}


def _extra_con_internos(nuevo, viejo):
    """`extra` de la fuente (`nuevo`, o el guardado si la sync no trae) con
    las claves EXTRA_INTERNO del `extra` guardado encima."""
    base = dict(nuevo) if isinstance(nuevo, dict) else dict(viejo or {})
    for clave in EXTRA_INTERNO:
        if clave in (viejo or {}):
            base[clave] = viejo[clave]
        else:
            base.pop(clave, None)
    return base


def upsert_producto(cliente, fuente, fuente_id, datos):
    """Crea o actualiza el producto (cliente, fuente, fuente_id). Solo toca
    las columnas presentes en `datos` — una sync parcial (p. ej. solo precio)
    no borra `fotos`/`descripcion` ya guardadas. `prioridad`, `en_prueba` y
    `activo_catalogo_id` son banderas del catálogo (marcar_producto) y una
    sync nunca las toca. `archivado`: un producto archivado por la sync
    (`extra.archivado_por == "sync"`, o sin marca) se desarchiva solo al
    reaparecer en la fuente; uno archivado a mano (`"manual"`) sigue
    archivado (sus datos sí se actualizan) hasta que la persona lo recupere.
    Las claves EXTRA_INTERNO de `extra` sobreviven al `extra` de la fuente."""
    ahora = db.ahora()
    valores = {k: v for k, v in (datos or {}).items() if k in _PRODUCTO_CAMPOS_DATOS}
    p = db.producto
    with db.conectar() as con:
        fila = con.execute(sa.select(p.c.id, p.c.archivado, p.c.extra).where(
            p.c.cliente == cliente, p.c.fuente == fuente, p.c.fuente_id == fuente_id)).first()
        if fila:
            pid, archivado, extra_viejo = fila[0], bool(fila[1]), dict(fila[2] or {})
            manual = archivado and extra_viejo.get("archivado_por") == "manual"
            extra = _extra_con_internos(valores.get("extra"), extra_viejo)
            if not manual:
                extra.pop("archivado_por", None)
            valores["extra"] = extra
            con.execute(p.update().where(p.c.id == pid)
                        .values(actualizado_en=ahora, archivado=manual, **valores))
            return pid
        valores["extra"] = _extra_con_internos(valores.get("extra"), {})
        return con.execute(p.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, fuente=fuente, fuente_id=fuente_id,
            prioridad=0, en_prueba=False, archivado=False, **valores)).inserted_primary_key[0]


def producto(cliente, producto_id):
    p = db.producto
    with db.conectar() as con:
        fila = con.execute(sa.select(p).where(p.c.id == producto_id, p.c.cliente == cliente)).first()
    return _producto_a_dict(fila) if fila else None


def producto_por_fuente(cliente, fuente, fuente_id):
    """El producto (cliente, fuente, fuente_id) tal como está guardado, o None.
    Lo usa el importador ANTES de `upsert_producto` para saber si va a crear
    o a actualizar (el upsert no lo distingue)."""
    p = db.producto
    with db.conectar() as con:
        fila = con.execute(sa.select(p).where(
            p.c.cliente == cliente, p.c.fuente == fuente, p.c.fuente_id == fuente_id)).first()
    return _producto_a_dict(fila) if fila else None


def productos(cliente, incluir_archivados=False):
    p = db.producto
    condiciones = [p.c.cliente == cliente]
    if not incluir_archivados:
        condiciones.append(p.c.archivado.is_(False))
    with db.conectar() as con:
        filas = con.execute(sa.select(p).where(*condiciones).order_by(p.c.prioridad.desc(), p.c.nombre))
        return [_producto_a_dict(f) for f in filas]


def por_activo(cliente):
    """{activo_catalogo_id: producto} de todas las filas del cliente que
    apuntan a un activo del catálogo, en UNA consulta — es lo que la pestaña
    Catálogo necesita para pintar precio/url/en prueba al lado de cada
    activo. Incluye archivadas (un activo cuya fila se archivó sigue siendo
    el mismo activo), pero si dos filas apuntan al mismo activo gana la que
    no está archivada."""
    p = db.producto
    mapa = {}
    with db.conectar() as con:
        filas = con.execute(sa.select(p).where(p.c.cliente == cliente, p.c.activo_catalogo_id.isnot(None))
                            .order_by(p.c.archivado.desc(), p.c.id))
        for f in filas:
            d = _producto_a_dict(f)
            actual = mapa.get(d["activo_catalogo_id"])
            if actual is None or (actual["archivado"] and not d["archivado"]):
                mapa[d["activo_catalogo_id"]] = d
    return mapa


def asegurar_manual(cliente, activo_id, nombre, descripcion=""):
    """La fila `producto` de un activo del catálogo de categoría producto,
    creándola si no existe (fuente `manual`, `fuente_id = activo_id`).
    Idempotente: si ya hay una fila con `activo_catalogo_id == activo_id`
    — la manual de antes, o una importada (csv/shopify…) que el importador
    enlazó al activo — se devuelve esa, sin tocarle nombre ni datos. Nunca
    dos filas para el mismo activo."""
    p = db.producto
    with db.conectar() as con:
        fila = con.execute(sa.select(p.c.id).where(p.c.cliente == cliente, p.c.activo_catalogo_id == activo_id)
                           .order_by(p.c.archivado, p.c.id)).first()
    if fila:
        return fila[0]
    pid = upsert_producto(cliente, "manual", activo_id, {"nombre": nombre, "descripcion": descripcion or ""})
    marcar_producto(cliente, pid, activo_catalogo_id=activo_id)
    return pid


def marcar_producto(cliente, producto_id, **campos):
    """Banderas del catálogo (y, desde Catálogo, `nombre`/`descripcion` del
    activo). `archivado=True` es un archivado MANUAL
    (`extra.archivado_por = "manual"`: la sync no lo deshace);
    `archivado=False` lo recupera y limpia la marca."""
    malos = set(campos) - set(_PRODUCTO_CAMPOS_MARCA)
    if malos:
        raise ValueError(f"Campos no permitidos: {sorted(malos)}")
    p = db.producto
    with db.conectar() as con:
        if "archivado" in campos:
            fila = con.execute(sa.select(p.c.extra).where(p.c.id == producto_id, p.c.cliente == cliente)).first()
            if not fila:
                return
            extra = dict(fila[0] or {})
            if campos["archivado"]:
                extra["archivado_por"] = "manual"
            else:
                extra.pop("archivado_por", None)
            campos = dict(campos, archivado=bool(campos["archivado"]), extra=extra)
        con.execute(p.update().where(p.c.id == producto_id, p.c.cliente == cliente)
                    .values(actualizado_en=db.ahora(), **campos))


def anotar_extra(cliente, producto_id, **claves):
    """Escribe claves EXTRA_INTERNO en `producto.extra` sin tocar el resto
    (None borra la clave). Solo claves internas: el `extra` de la fuente lo
    escribe la sync."""
    malas = set(claves) - set(EXTRA_INTERNO)
    if malas:
        raise ValueError(f"Claves no permitidas: {sorted(malas)}")
    p = db.producto
    with db.conectar() as con:
        fila = con.execute(sa.select(p.c.extra).where(p.c.id == producto_id, p.c.cliente == cliente)).first()
        if not fila:
            return
        extra = dict(fila[0] or {})
        for clave, valor in claves.items():
            if valor is None:
                extra.pop(clave, None)
            else:
                extra[clave] = valor
        con.execute(p.update().where(p.c.id == producto_id, p.c.cliente == cliente).values(extra=extra))


def _archivar_en(con, condiciones, por, ahora):
    """Archiva fila por fila (hay que reescribir `extra` con `archivado_por`).
    Devuelve cuántas."""
    p = db.producto
    filas = con.execute(sa.select(p.c.id, p.c.extra).where(*condiciones)).all()
    for pid, extra in filas:
        extra = dict(extra or {})
        extra["archivado_por"] = por
        con.execute(p.update().where(p.c.id == pid).values(archivado=True, actualizado_en=ahora, extra=extra))
    return len(filas)


def archivar_faltantes(cliente, fuente, ids_vistos):
    """Archiva (por sync: `extra.archivado_por = "sync"`) los productos de
    `fuente` que no aparecieron en la última sync (su fuente_id no está en
    `ids_vistos`) y que todavía no lo estaban. Devuelve cuántos se archivaron."""
    ids_vistos = set(ids_vistos or [])
    p = db.producto
    condiciones = [p.c.cliente == cliente, p.c.fuente == fuente, p.c.archivado.is_(False)]
    if ids_vistos:
        condiciones.append(p.c.fuente_id.not_in(ids_vistos))
    with db.conectar() as con:
        return _archivar_en(con, condiciones, "sync", db.ahora())


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


# Un pedido con utm que no se pudo ligar en 30 días (utm ajeno, experimento
# ya cerrado) deja de reintentarse: sin este tope la cola crecería con cada
# utm foráneo y cada sync la volvería a recorrer entera.
DIAS_RESOLVER_PEDIDOS = 30


def pedidos_sin_resolver(cliente, dias=DIAS_RESOLVER_PEDIDOS):
    """Pedidos con `utm_content` (llegaron con una pieza en la URL) de los
    últimos `dias` que todavía no se ligaron a un `experimento_pieza_id` —
    la cola que debe resolver el atribuidor del Bloque 5."""
    pe = db.pedido
    desde = (datetime.now() - timedelta(days=dias)).isoformat(timespec="seconds")
    with db.conectar() as con:
        filas = con.execute(sa.select(pe).where(
            pe.c.cliente == cliente, pe.c.utm_content.isnot(None), pe.c.experimento_pieza_id.is_(None),
            pe.c.fecha >= desde)
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


def pedidos_por_experimento(cliente):
    """{experimento_id: pedidos atribuidos a alguna de sus piezas} en UNA
    consulta — es lo que la pestaña Experimentos muestra como «ventas por
    tienda» sin ir a la base una vez por experimento. Solo experimentos con
    al menos un pedido aparecen en el dict."""
    pe, ep = db.pedido, db.experimento_pieza
    q = (sa.select(ep.c.experimento_id, sa.func.count(pe.c.id))
         .select_from(pe.join(ep, ep.c.id == pe.c.experimento_pieza_id))
         .where(pe.c.cliente == cliente, ep.c.cliente == cliente)
         .group_by(ep.c.experimento_id))
    with db.conectar() as con:
        return {int(eid): int(n) for eid, n in con.execute(q)}


def ventas_por_pieza(cliente, ep_id, desde_iso):
    """Compras, ingresos (suma de `total`) y `monedas` (las distintas que
    traían esos pedidos, ordenadas) de una pieza desde `desde_iso`
    (comparación lexicográfica — funciona porque `fecha` es ISO de 19
    caracteres, igual que el resto del motor). Los ingresos se suman tal
    cual, sin convertir: quien los use tiene que mirar `monedas` antes de
    compararlos con un gasto en otra moneda."""
    pe = db.pedido
    filtro = (pe.c.cliente == cliente, pe.c.experimento_pieza_id == ep_id, pe.c.fecha >= desde_iso)
    with db.conectar() as con:
        fila = con.execute(sa.select(
            sa.func.count(pe.c.id), sa.func.coalesce(sa.func.sum(pe.c.total), 0.0)).where(*filtro)).first()
        monedas = con.execute(sa.select(pe.c.moneda).where(*filtro).distinct()).scalars().all()
    return {"compras": int(fila[0] or 0), "ingresos": float(fila[1] or 0.0),
            "monedas": sorted(monedas, key=lambda m: m or "")}
