import pytest

from tests.test_experimentos_db import PAISES


def test_tabla_de_puertas():
    import modos
    assert modos.resolver("manual", "pausar") == "propuesta"
    assert modos.resolver("semi", "pausar") == "ejecutar"
    assert modos.resolver("semi", "escalar") == "propuesta"
    assert modos.resolver("semi", "derivar") == "propuesta"
    assert modos.resolver("auto", "derivar") == "ejecutar"
    assert modos.resolver("auto", "activar") == "ejecutar"
    assert modos.resolver("manual", "archivar") == "propuesta" and modos.resolver("semi", "archivar") == "ejecutar"
    with pytest.raises(ValueError):
        modos.resolver("otro", "pausar")


def test_propuestas_crud(base_temporal):
    import experimentos as ex
    import propuestas as pr
    eid = ex.crear("acme", "X", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    p1 = pr.crear("acme", eid, "escalar", {"pais": "CO", "ep_id": 5}, "ganador")
    assert pr.crear("acme", eid, "escalar", {"pais": "CO", "ep_id": 5}, "ganador") == p1
    p2 = pr.crear("acme", eid, "pausar", {"ep_id": 6}, "perdedor")
    assert [p["accion"] for p in pr.pendientes("acme", eid)] == ["escalar", "pausar"]
    assert pr.pendientes("otro") == []
    r = pr.resolver("acme", p2, "rechazada")
    assert r["estado"] == "rechazada" and r["resuelta_en"]
    assert pr.resolver("acme", p2, "aprobada") is None   # ya resuelta
    aprobadas = pr.aprobar_todas("acme", eid)
    assert [p["id"] for p in aprobadas] == [p1]
    pr.marcar_ejecutada("acme", p1)
    assert pr.pendientes("acme", eid) == []
    assert ex.obtener("acme", eid)["propuestas_pendientes"] == 0


def test_crear_hijo(base_temporal):
    import experimentos as ex
    eid = ex.crear("acme", "Padre", PAISES, "OUTCOME_TRAFFIC", 7, 500.0, "https://t", "COP", modo="auto")
    ex.actualizar("acme", eid, reglas={"ctr_min": 2.0})
    hijo = ex.crear_hijo("acme", eid, "Padre · derivado", 42)
    h = ex.obtener("acme", hijo)
    assert h["estado"] == "armando" and h["modo"] == "auto" and h["reglas"] == {"ctr_min": 2.0}
    assert [p["pais"] for p in h["paises"]] == ["CO", "MX"] and all(p["meta_adset_id"] is None for p in h["paises"])
    assert h["padre_experimento_id"] == eid and h["extra"]["origen_ep_id"] == 42
    assert ex.obtener("acme", eid)["hijos"] == [hijo]


def test_crear_hijo_copia_producto_id(base_temporal):
    """M6: el spec usa producto_id para no volver a proponer el mismo
    concepto para ese producto en el hijo — así que el hijo debe heredarlo
    del padre."""
    import sqlalchemy as sa

    import experimentos as ex
    db = base_temporal
    with db.conectar() as con:
        producto_id = con.execute(db.producto.insert().values(
            cliente="acme", creado_en=db.ahora(), actualizado_en=db.ahora(),
            fuente="manual", nombre="Cojín abrazable")).inserted_primary_key[0]
    eid = ex.crear("acme", "Padre", PAISES, "OUTCOME_TRAFFIC", 7, 500.0, "https://t", "COP")
    with db.conectar() as con:
        con.execute(db.experimento.update().where(db.experimento.c.id == eid).values(producto_id=producto_id))
    hijo = ex.crear_hijo("acme", eid, "Padre · derivado", 42)
    with db.conectar() as con:
        heredado = con.execute(sa.select(db.experimento.c.producto_id).where(db.experimento.c.id == hijo)).scalar()
    assert heredado == producto_id


def test_crear_hijo_profundidad_tope_restante_e_idempotente(base_temporal):
    """I-9 + I-6: el hijo lleva `profundidad` = padre + 1 y su tope es lo que
    le queda al padre (mínimo 0); repetir crear_hijo para la misma pieza
    devuelve el mismo hijo (no hay dos hijos por una pieza)."""
    import experimentos as ex
    eid = ex.crear("acme", "Raíz", PAISES, "OUTCOME_TRAFFIC", 7, 500.0, "https://t", "COP", modo="auto")
    ex.actualizar("acme", eid, gasto_acumulado=120.0)
    assert ex.profundidad(ex.obtener("acme", eid)) == 0
    hijo = ex.crear_hijo("acme", eid, "Hijo", 42)
    assert ex.crear_hijo("acme", eid, "Hijo otra vez", 42) == hijo
    assert ex.crear_hijo("acme", eid, "Hijo de otra pieza", 43) != hijo
    h = ex.obtener("acme", hijo)
    assert h["extra"]["profundidad"] == 1 and h["tope_total"] == 380.0 and ex.profundidad(h) == 1
    ex.actualizar("acme", hijo, gasto_acumulado=900.0)
    nieto = ex.crear_hijo("acme", hijo, "Nieto", 77)
    n = ex.obtener("acme", nieto)
    assert n["extra"]["profundidad"] == 2 and n["tope_total"] == 0.0
    with pytest.raises(ValueError):
        ex.crear_hijo("acme", 999999, "x", 1)
