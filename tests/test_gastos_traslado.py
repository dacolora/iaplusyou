"""PND-314 y PND-318 (decisión 2026-10-13, lote 1): lo que el proveedor cobró y al cliente no se le cobró
(un `no_cobrado`, o un `cobro` con su `reverso`) se le cobra cuando por fin se entrega o se reusa: el costo
pasa de su fila a la de la entrega, sin pagarle dos veces al proveedor ni contar dos veces el costo."""
import pytest
import sqlalchemy as sa

pytestmark = pytest.mark.usefixtures("margen_1_5")


def _movs(db, gasto_id=None):
    m = db.movimiento_saldo
    q = sa.select(m).order_by(m.c.id)
    if gasto_id is not None:
        q = q.where(m.c.gasto_id == gasto_id)
    with db.conectar() as con:
        return con.execute(q).all()


def _fila(db, ref, cliente="acme"):
    with db.conectar() as con:
        return con.execute(sa.select(db.gasto).where(db.gasto.c.cliente == cliente,
                                                     db.gasto.c.referencia == ref)).first()


def _total(db, cliente="acme"):
    with db.conectar() as con:
        return round(con.execute(sa.select(sa.func.sum(db.gasto.c.usd))
                                 .where(db.gasto.c.cliente == cliente)).scalar() or 0, 4)


def test_lo_no_cobrado_se_cobra_al_entregarlo_y_el_costo_no_se_duplica(base_temporal):
    import gastos
    from cobros import libro
    libro.configurar("acme", usuario="admin", cobrar=True)
    gastos.registrar("acme", "swap", 4.0, "swap:s1:t1", entregado=False)   # la espera se agotó: no_cobrado
    gid, movido = gastos.registrar_trasladando("acme", "swap", 0, "swap:s1:t2", [{"referencia": "swap:s1:t1"}],
                                               detalle="recuperado")
    assert movido == 4.0
    assert _fila(base_temporal, "swap:s1:t2").usd == 4.0
    assert _fila(base_temporal, "swap:s1:t1").usd == 0.0
    assert _total(base_temporal) == 4.0                                   # se pagó una vez y se anota una vez
    (cobro,) = _movs(base_temporal, gid)
    assert (cobro.tipo, cobro.milesimas) == ("cobro", -6000)
    origen = _fila(base_temporal, "swap:s1:t1")
    assert origen.extra["trasladado"][0]["a"] == "swap:s1:t2"
    # Repetirlo no vuelve a mover nada (el origen ya quedó en 0).
    _, otra_vez = gastos.registrar_trasladando("acme", "swap", 0, "swap:s1:t3", [{"referencia": "swap:s1:t1"}])
    assert otra_vez == 0 and _fila(base_temporal, "swap:s1:t3") is None


def test_un_cobro_revertido_tambien_esta_pendiente(base_temporal):
    import gastos
    from cobros import libro
    libro.configurar("acme", usuario="admin", cobrar=True)
    with libro.en_trabajo(1, "job-1"):
        gastos.registrar("acme", "guion", 0.05, "guion:cf1:t1")
    libro.revertir_trabajo("acme", "job-1", "falló")
    _, movido = gastos.registrar_trasladando("acme", "final", 0.2, "final:cf1__es_CO:t2",
                                             [{"referencia": "guion:cf1:t1"}])
    assert movido == 0.05
    assert _fila(base_temporal, "final:cf1__es_CO:t2").usd == 0.25
    viejo = _fila(base_temporal, "guion:cf1:t1")
    assert viejo.usd == 0.0
    assert sum(m.milesimas for m in _movs(base_temporal, viejo.id)) == 0      # cobro y reverso siguen en par
    assert sum(m.milesimas for m in _movs(base_temporal)) == -int(0.25 * 1.5 * 1000)


def test_lo_que_ya_se_cobro_no_se_mueve(base_temporal):
    import gastos
    from cobros import libro
    libro.configurar("acme", usuario="admin", cobrar=True)
    gastos.registrar("acme", "guion", 0.05, "guion:cf1:t1")              # cobrado y entregado
    _, movido = gastos.registrar_trasladando("acme", "final", 0.2, "final:x:t2", [{"referencia": "guion:cf1:t1"}])
    assert movido == 0 and _fila(base_temporal, "guion:cf1:t1").usd == 0.05
    assert _fila(base_temporal, "final:x:t2").usd == 0.2


def test_un_proyecto_que_no_cobra_no_mueve_nada(base_temporal):
    import gastos
    gastos.registrar("acme", "swap", 4.0, "swap:s1:t1", entregado=False)
    _, movido = gastos.registrar_trasladando("acme", "swap", 0, "swap:s1:t2", [{"referencia": "swap:s1:t1"}])
    assert movido == 0
    assert _fila(base_temporal, "swap:s1:t1").usd == 4.0 and _fila(base_temporal, "swap:s1:t2") is None


def test_con_clave_se_mueve_solo_esa_parte(base_temporal):
    import gastos
    from cobros import libro
    libro.configurar("acme", usuario="admin", cobrar=True)
    gastos.registrar("acme", "final", 0.30, "final:cf1__es_CO:t1", entregado=False,
                     extra={"cache": {"borrador:7": 0.10, "destino:7:en_US": 0.20}})
    _, movido = gastos.registrar_trasladando("acme", "final", 0.05, "final:cf1__es_CO:t2",
                                             [{"referencia": "final:cf1__es_CO:t1", "clave": "borrador:7"}])
    assert movido == 0.10
    viejo = _fila(base_temporal, "final:cf1__es_CO:t1")
    assert viejo.usd == 0.20 and viejo.extra["cache"] == {"destino:7:en_US": 0.20}
    assert _fila(base_temporal, "final:cf1__es_CO:t2").usd == 0.15
    # La misma clave no se cobra dos veces.
    _, otra_vez = gastos.registrar_trasladando("acme", "final", 0.05, "final:cf1__es_CO:t3",
                                               [{"referencia": "final:cf1__es_CO:t1", "clave": "borrador:7"}])
    assert otra_vez == 0


def test_no_toca_las_filas_de_otro_proyecto(base_temporal):
    import gastos
    from cobros import libro
    libro.configurar("acme", usuario="admin", cobrar=True)
    libro.configurar("otro", usuario="admin", cobrar=True)
    gastos.registrar("otro", "swap", 4.0, "swap:s1:t1", entregado=False)
    _, movido = gastos.registrar_trasladando("acme", "swap", 0, "swap:s1:t2", [{"referencia": "swap:s1:t1"}])
    assert movido == 0 and _fila(base_temporal, "swap:s1:t1", cliente="otro").usd == 4.0


def test_pendientes_por_clave(base_temporal):
    import gastos
    from cobros import libro
    libro.configurar("acme", usuario="admin", cobrar=True)
    gastos.registrar("acme", "final", 0.30, "final:cf1__es_CO:t1", entregado=False,
                     extra={"cache": {"borrador:7": 0.10, "destino:7:en_US": 0.20}})
    gastos.registrar("acme", "final", 0.30, "final:cf2__es_CO:t1", entregado=False,
                     extra={"cache": {"borrador:9": 0.30}})
    gastos.registrar("acme", "guion", 0.05, "guion:cf1:t1", extra={"cache": {"guion_base:cf1": 0.05}})  # cobrado
    encontrados = gastos.pendientes_por_clave("acme", ("final:cf1__", "guion:cf1"),
                                              {"borrador:7", "destino:7:en_US", "guion_base:cf1"})
    assert sorted((t["referencia"], t["clave"]) for t in encontrados) == [
        ("final:cf1__es_CO:t1", "borrador:7"), ("final:cf1__es_CO:t1", "destino:7:en_US")]


def test_la_version_segura_anota_la_entrega_si_el_traslado_falla(base_temporal, monkeypatch):
    import gastos
    monkeypatch.setattr(gastos, "registrar_trasladando", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    gid, movido = gastos.registrar_trasladando_seguro("acme", "final", 0.2, "final:x:t2", [{"referencia": "y"}])
    assert gid and movido == 0.0 and _fila(base_temporal, "final:x:t2").usd == 0.2
