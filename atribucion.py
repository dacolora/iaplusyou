"""
Atribución por tienda (Bloque 5): liga los pedidos que llegaron con
`utm_content=<experimento_pieza.id>` (ver lanzador.url_destino) a la
`experimento_pieza` que los generó, y cuenta las ventas de una pieza desde
que se activó. Es lo que `lanzador.refrescar` mezcla en el snapshot cuando
el experimento tiene `atribucion == "tienda"` en vez de creer en las compras
que reporta Meta.

Por qué el ep id y no el pieza.id (el plan original decía pieza_id): el
mismo clon en dos países son dos `experimento_pieza` con dos anuncios, y
con solo el pieza.id todas las ventas caían en una sola (la más nueva) —
el otro país quedaba en 0 compras. El ep id es único por
experimento+pieza+país. Los links publicados antes de este cambio siguen
llevando un pieza.id: por eso `resolver_pendientes` prueba primero como ep
id y, si ningún ep del cliente tiene ese id, cae al criterio viejo.

Solo datos: importa `tiendas`, `db` y SQLAlchemy — nada de Meta ni de la
app, para que lanzador.py pueda importarlo al nivel del módulo sin ciclos.
"""
import sqlalchemy as sa

import db
import tiendas


def _numero(utm_content):
    """El id que viaja en utm_content, o None si no es numérico (un utm de
    otra campaña, o uno con formato distinto)."""
    texto = str(utm_content or "").strip()
    return int(texto) if texto.isdigit() else None


def _ep_para_pieza(con, cliente, pieza_id):
    """Fallback para links viejos (utm_content=pieza.id): la
    `experimento_pieza` más reciente de esa pieza cuyo experimento no está
    `cerrado`, del mismo cliente (un pedido nunca se atribuye a una pieza
    ajena: la pieza ajena no aparece porque `ep.cliente` no coincide)."""
    ep, e = db.experimento_pieza, db.experimento
    return con.execute(
        sa.select(ep.c.id).select_from(ep.join(e, e.c.id == ep.c.experimento_id))
        .where(ep.c.cliente == cliente, ep.c.pieza_id == pieza_id, e.c.estado != "cerrado")
        .order_by(ep.c.id.desc()).limit(1)).scalar()


def _resolver_id(con, cliente, numero):
    """ep id al que va un utm numérico, o None si no se puede ligar. Primero
    como `experimento_pieza.id` del cliente: si existe, manda ese (y si su
    experimento ya cerró, queda sin resolver — un ep real nunca se
    reinterpreta como pieza.id). Si no hay ep con ese id, es un link viejo
    con pieza.id."""
    ep, e = db.experimento_pieza, db.experimento
    fila = con.execute(
        sa.select(e.c.estado).select_from(ep.join(e, e.c.id == ep.c.experimento_id))
        .where(ep.c.id == numero, ep.c.cliente == cliente)).first()
    if fila is not None:
        return numero if fila[0] != "cerrado" else None
    return _ep_para_pieza(con, cliente, numero)


def resolver_pendientes(cliente):
    """Resuelve `tiendas.pedidos_sin_resolver`: utm_content numérico →
    `experimento_pieza.id` del cliente (experimento no cerrado) o, si no hay
    ep con ese id, pieza.id → experimento_pieza abierta más reciente (links
    viejos) → `tiendas.resolver_pedido`. Un utm no numérico o un id sin
    experimento abierto quedan sin resolver (la próxima sync lo vuelve a
    intentar: la pieza puede entrar a un experimento después). Devuelve
    cuántos pedidos ligó."""
    pendientes = tiendas.pedidos_sin_resolver(cliente)
    if not pendientes:
        return 0
    # Una consulta por id distinto, no por pedido (el mismo anuncio suele
    # traer muchos pedidos), y luego los UPDATE uno a uno vía tiendas.
    por_id = {}
    ligar = []
    with db.conectar() as con:
        for ped in pendientes:
            numero = _numero(ped["utm_content"])
            if numero is None:
                continue
            if numero not in por_id:
                por_id[numero] = _resolver_id(con, cliente, numero)
            if por_id[numero] is not None:
                ligar.append((ped["id"], por_id[numero]))
    return sum(1 for pedido_id, ep_id in ligar if tiendas.resolver_pedido(cliente, pedido_id, ep_id))


def ventas_tienda(cliente, ep):
    """Compras, ingresos y monedas de una pieza (dict de experimentos.piezas)
    desde que se activó (`extra.activado_en`) o, si nunca se activó sola,
    desde que entró al experimento (`creado_en`). Ingresos en la moneda de la
    tienda, tal cual la guardó el conector — nunca se convierten."""
    desde = (ep.get("extra") or {}).get("activado_en") or ep["creado_en"]
    return tiendas.ventas_por_pieza(cliente, ep["id"], desde)
