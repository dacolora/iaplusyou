import pytest

from tests.test_experimentos_db import PAISES, _pieza


@pytest.fixture()
def ent(base_temporal, monkeypatch):
    import acciones
    import experimentos as ex
    llamadas = []
    monkeypatch.setattr(acciones.lanzador, "pausar_pieza", lambda c, ep: llamadas.append(("pausar", ep)))
    monkeypatch.setattr(acciones.lanzador, "activar_pieza", lambda c, ep: llamadas.append(("activar", ep)))
    monkeypatch.setattr(acciones.lanzador, "cambiar_estado", lambda c, e, s, pais=None: llamadas.append(("estado", e, s)))
    monkeypatch.setattr(acciones.lanzador, "escalar_pais", lambda c, e, p, pct, tope_dia=None: (llamadas.append(("escalar", p, pct, tope_dia)), 24.0)[1])
    monkeypatch.setattr(acciones.derivaciones, "planificar", lambda c, e, tipo, payload: (llamadas.append(("planificar", tipo, payload.get("ep_id"))), 99)[1])
    pid = _pieza(base_temporal)
    eid = ex.crear("acme", "X", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP", modo="semi")
    ep = ex.agregar_pieza("acme", eid, pid, "CO")
    ex.actualizar_pieza("acme", ep, meta_ad_id="ad1", estado="activo")
    ex.actualizar("acme", eid, estado="corriendo", meta_campaign_id="c1")
    return {"ac": acciones, "ex": ex, "eid": eid, "ep": ep, "pid": pid, "llamadas": llamadas}


def test_pedir_respeta_modo(ent):
    ac, ex, eid, ep = ent["ac"], ent["ex"], ent["eid"], ent["ep"]
    import propuestas as pr
    assert ac.pedir("acme", eid, "pausar", {"ep_id": ep}, "perdedor")[0] == "ejecutada"
    assert ent["llamadas"][-1] == ("pausar", ep)
    assert ac.pedir("acme", eid, "escalar", {"pais": "CO", "ep_id": ep}, "ganador")[0] == "propuesta"
    assert [p["accion"] for p in pr.pendientes("acme", eid)] == ["escalar"]
    ex.actualizar("acme", eid, modo="auto")
    assert ac.pedir("acme", eid, "escalar", {"pais": "CO", "ep_id": ep}, "ganador")[0] == "ejecutada"
    assert ent["llamadas"][-1][0] == "escalar"
    tipos = [e["tipo"] for e in ex.eventos("acme", eid)]
    assert "accion" in tipos and "propuesta" in tipos


def test_pedir_con_tope_alcanzado_propone_aunque_sea_auto(ent):
    ac, ex, eid, ep = ent["ac"], ent["ex"], ent["eid"], ent["ep"]
    ex.actualizar("acme", eid, modo="auto", gasto_acumulado=100.0)
    estado, msg = ac.pedir("acme", eid, "escalar", {"pais": "CO", "ep_id": ep}, "ganador")
    assert estado == "propuesta" and "tope" in msg.lower()
    assert ac.pedir("acme", eid, "pausar", {"ep_id": ep}, "x")[0] == "ejecutada"   # pausar no gasta


def test_ejecutar_derivar_rescatar_archivar_idempotentes(ent, monkeypatch):
    ac, ex, eid, ep = ent["ac"], ent["ex"], ent["eid"], ent["ep"]
    import creative_flow as cf
    ac.ejecutar("acme", eid, "derivar", {"ep_id": ep})
    ac.ejecutar("acme", eid, "derivar", {"ep_id": ep})
    assert [l for l in ent["llamadas"] if l[0] == "planificar"] == [("planificar", "derivar", ep)]
    ac.ejecutar("acme", eid, "rescatar", {"ep_id": ep})
    ac.ejecutar("acme", eid, "rescatar", {"ep_id": ep})
    assert [l for l in ent["llamadas"] if l == ("planificar", "rescatar", ep)] == [("planificar", "rescatar", ep)]
    p = [p for p in ex.piezas("acme", eid) if p["id"] == ep][0]
    assert p["extra"]["derivado"] is True and p["extra"]["rescatado_en_escalon"] == 1
    archivados = []
    monkeypatch.setattr(cf, "archivar_concepto", lambda c, cf_id, motivo: archivados.append((cf_id, motivo)))
    ac.ejecutar("acme", eid, "archivar", {"ep_id": ep, "cf_id": "cf_1", "motivo": "perdió 3 escalones"})
    assert archivados == [("cf_1", "perdió 3 escalones")] and ("pausar", ep) in ent["llamadas"]


def test_ejecutar_activar(ent):
    ac, ex, eid, ep = ent["ac"], ent["ex"], ent["eid"], ent["ep"]
    ex.actualizar("acme", eid, estado="pausado")
    ac.ejecutar("acme", eid, "activar", {"ep_ids": [ep]})
    assert ("estado", eid, "ACTIVE") in ent["llamadas"] and ("activar", ep) in ent["llamadas"]
