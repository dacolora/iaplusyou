"""Planes mensuales (spec planes 2026-10-09 §1-§4). ÚNICO escritor de `plan`,
`suscripcion`, `periodo_plan` y `pago_plan` (la Task 5 trae el alta, el cobro del
periodo, la renovación y la gracia). Los movimientos del libro que acreditan o
vencen un periodo los escribe `cobros.libro` (`acreditar_plan`, `vencer_periodo`);
este módulo marca el periodo `cerrado` en la misma transacción (`marcar_cerrado`).

No importa `cobros.libro` al cargar: el libro importa este módulo."""
import logging

import sqlalchemy as sa

import db

log = logging.getLogger(__name__)

# Lo «barato» que el plan regala hasta el tope de uso justo (spec §4): los tipos de gasto de Claude y de la
# transcripción. Cada nombre es de `gastos.TIPOS` (`tests/test_planes_libro.py` lo vigila). Del spec: «leer_referente»
# no es un tipo de gasto (la lectura de «Recrear fiel» se anota como `adaptar_referente`, referentes/rutas.py) y el
# diagnóstico de una perdedora se anota como `revision` (tareas/experimentos._diagnosticar). Nunca entran `recoleccion`
# (Apify cobra en dólares) ni video, imagen, voz o música.
TIPOS_INCLUIDOS = frozenset({
    "guion", "regla_producto", "caption_organico", "adaptar_referente", "sugerir_ia", "clasificacion",
    "refinar_prompt", "guion_clips", "ideas", "pedidos", "revision", "evaluacion", "transcripcion",
})

# Tipo de tarea del worker → el tipo de gasto que anota, solo donde TODO lo que la tarea paga es incluido (para que
# `trabajos.encolar` le pase el `tipo` a `libro.exigir` y lo incluido dentro del tope no pida saldo). Una tarea que
# no está aquí se frena como siempre (sin `tipo`).
GASTO_DE_TAREA = {
    "final_guion": "guion",                    # final_edition.preparar_guion
    "producto_pedidos": "pedidos",             # tareas/doctrina.py
    "pieza_revisar": "revision",               # tareas/doctrina.py
    "sprint_reescribir_idea": "ideas",         # tareas/sprints.py
    "sprint_proponer_ideas": "ideas",          # tareas/sprints.py
    "sprint_qa_pieza": "revision",             # tareas/sprints._gasto_qa
    "referentes_sugerir_ia": "sugerir_ia",     # tareas/sprints.py
    "referentes_clasificar": "clasificacion",  # tareas/referentes.py
    "tw_evaluar": "evaluacion",                # tareas/triple_whale.py
    "tw_analizar_anuncio": "evaluacion",       # Whisper (transcripcion) + Claude (evaluacion): las dos incluidas
    "material_transcribir": "transcripcion",   # final_edition/transcripcion.py
    "catalogo_importar": "regla_producto",     # importador.vincular_activo → la regla de fidelidad
    "producto_vincular": "regla_producto",
}

EPSILON_USD = 1e-9   # 0,20 + 0,05 = 0,25000000000000006: el tope justo cabe


def _desde_fila(f):
    return {"id": int(f.id), "inicio": f.inicio, "fin": f.fin, "margen": float(f.margen),
            "tope_incluido_usd": float(f.tope_incluido_usd), "credito_milesimas": int(f.credito_milesimas),
            "suscripcion_id": int(f.suscripcion_id)}


def _leer_periodo(con, cliente, ahora):
    p = db.periodo_plan
    fila = con.execute(sa.select(p).where(p.c.cliente == cliente, p.c.cerrado == sa.false(),
                                          p.c.inicio <= ahora, p.c.fin > ahora)
                       .order_by(p.c.inicio.desc(), p.c.id.desc()).limit(1)).first()
    return _desde_fila(fila) if fila is not None else None


def periodo_abierto(con, cliente=None, ahora=None):
    """El periodo vigente de `cliente` (inicio ≤ ahora < fin, sin cerrar) o None.

    Forma canónica `periodo_abierto(con, cliente, ahora=None)`: con `con` lee en
    esa transacción (el libro, con su candado) y nunca memoriza. Con `con=None`
    (o la forma corta `periodo_abierto(cliente)`) abre su conexión y, dentro de
    una petición de Flask y sin `ahora` explícito, la lectura queda en `flask.g`
    para el resto de ESA petición (nunca entre peticiones)."""
    if isinstance(con, str) and cliente is None:
        con, cliente = None, con
    if not cliente:
        return None
    if con is not None:
        return _leer_periodo(con, cliente, ahora or db.ahora())
    if ahora is not None:
        with db.conectar() as c:
            return _leer_periodo(c, cliente, ahora)
    return _memo(("periodo", cliente), lambda: _leer_periodo_nuevo(cliente))


def _leer_periodo_nuevo(cliente):
    with db.conectar() as c:
        return _leer_periodo(c, cliente, db.ahora())


def _memo(clave, calcular):
    """Como `cobros.vista._memo`: una lectura por petición, en `flask.g`."""
    try:
        from flask import g, has_request_context  # noqa: PLC0415
        if has_request_context():
            cache = g.setdefault("_cobros_planes", {})
            if clave not in cache:
                cache[clave] = calcular()
            return cache[clave]
    except RuntimeError:
        pass
    return calcular()


def periodo(con, periodo_id):
    """Un periodo por id (abierto o no), o None. Solo lee."""
    p = db.periodo_plan
    fila = con.execute(sa.select(p).where(p.c.id == int(periodo_id))).first()
    if fila is None:
        return None
    return {**_desde_fila(fila), "cliente": fila.cliente, "cerrado": bool(fila.cerrado)}


def _incluido_usado(con, cliente, periodo_):
    m = db.movimiento_saldo
    total = con.execute(sa.select(sa.func.coalesce(sa.func.sum(sa.func.json_extract(m.c.extra, "$.costo")), 0))
                        .where(m.c.cliente == cliente, m.c.tipo == "incluido",
                               m.c.creado_en >= periodo_["inicio"], m.c.creado_en < periodo_["fin"])).scalar()
    return float(total or 0)


def incluido_usado(cliente, periodo_, con=None):
    """Costo de proveedor (USD) de lo incluido en `periodo_` (un dict de
    `periodo_abierto`): la suma de `extra.costo` de los movimientos `incluido`."""
    if not periodo_:
        return 0.0
    if con is not None:
        return _incluido_usado(con, cliente, periodo_)
    with db.conectar() as c:
        return _incluido_usado(c, cliente, periodo_)


def cabe_incluido(usado, costo, periodo_):
    return float(usado) + float(costo or 0) <= float(periodo_["tope_incluido_usd"]) + EPSILON_USD


def marcar_cerrado(con, periodo_id):
    """El periodo ya se venció (`libro.vencer_periodo` escribió su movimiento en
    esta misma transacción). Devuelve las filas tocadas."""
    p = db.periodo_plan
    return con.execute(p.update().where(p.c.id == int(periodo_id)).values(cerrado=True)).rowcount
