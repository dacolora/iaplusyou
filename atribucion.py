"""
Atribución por tienda (Bloque 5): liga los pedidos que llegaron con
`utm_content=<pieza.id>` (ver lanzador.url_destino) a la `experimento_pieza`
que los generó, y cuenta las ventas de una pieza desde que se activó. Es lo
que `lanzador.refrescar` mezcla en el snapshot cuando el experimento tiene
`atribucion == "tienda"` en vez de creer en las compras que reporta Meta.

Solo datos: importa `tiendas`, `db` y SQLAlchemy — nada de Meta ni de la
app, para que lanzador.py pueda importarlo al nivel del módulo sin ciclos.
"""
import sqlalchemy as sa

import db
import tiendas


def _pieza_id(utm_content):
    """El `pieza.id` que viaja en utm_content, o None si no es numérico (un
    utm de otra campaña, o uno viejo con formato distinto)."""
    texto = str(utm_content or "").strip()
    return int(texto) if texto.isdigit() else None


def _ep_para_pieza(con, cliente, pieza_id):
    """La `experimento_pieza` más reciente de esa pieza cuyo experimento no
    está `cerrado`, del mismo cliente (un pedido nunca se atribuye a una
    pieza ajena: la pieza ajena no aparece porque `ep.cliente` no coincide)."""
    ep, e = db.experimento_pieza, db.experimento
    return con.execute(
        sa.select(ep.c.id).select_from(ep.join(e, e.c.id == ep.c.experimento_id))
        .where(ep.c.cliente == cliente, ep.c.pieza_id == pieza_id, e.c.estado != "cerrado")
        .order_by(ep.c.id.desc()).limit(1)).scalar()


def resolver_pendientes(cliente):
    """Resuelve `tiendas.pedidos_sin_resolver`: utm_content numérico →
    pieza → experimento_pieza abierta más reciente → `tiendas.resolver_pedido`.
    Un utm no numérico o una pieza sin experimento abierto quedan sin
    resolver (la próxima sync lo vuelve a intentar: la pieza puede entrar a
    un experimento después). Devuelve cuántos pedidos ligó."""
    pendientes = tiendas.pedidos_sin_resolver(cliente)
    if not pendientes:
        return 0
    # Una consulta por pieza distinta, no por pedido (la misma pieza suele
    # traer muchos pedidos), y luego los UPDATE uno a uno vía tiendas.
    por_pieza = {}
    ligar = []
    with db.conectar() as con:
        for ped in pendientes:
            pieza_id = _pieza_id(ped["utm_content"])
            if pieza_id is None:
                continue
            if pieza_id not in por_pieza:
                por_pieza[pieza_id] = _ep_para_pieza(con, cliente, pieza_id)
            if por_pieza[pieza_id] is not None:
                ligar.append((ped["id"], por_pieza[pieza_id]))
    return sum(1 for pedido_id, ep_id in ligar if tiendas.resolver_pedido(cliente, pedido_id, ep_id))


def ventas_tienda(cliente, ep):
    """Compras e ingresos de una pieza (dict de experimentos.piezas) desde que
    se activó (`extra.activado_en`) o, si nunca se activó sola, desde que
    entró al experimento (`creado_en`). Ingresos en la moneda de la tienda,
    tal cual la guardó el conector — nunca se convierten."""
    desde = (ep.get("extra") or {}).get("activado_en") or ep["creado_en"]
    return tiendas.ventas_por_pieza(cliente, ep["id"], desde)
