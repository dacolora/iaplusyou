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
