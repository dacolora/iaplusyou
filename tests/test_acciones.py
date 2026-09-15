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


def test_ejecutar_activar_acepta_experimento_decidido(ent):
    """I-1 del review de decidir: un rescate aprobado después de que el
    experimento pasó a 'decidido' tiene que poder activarse en Meta — si no,
    la propuesta aprobada queda inejecutable."""
    ac, ex, eid, ep = ent["ac"], ent["ex"], ent["eid"], ent["ep"]
    ex.actualizar("acme", eid, estado="decidido")
    ac.ejecutar("acme", eid, "activar", {"ep_ids": [ep]})
    assert ("activar", ep) in ent["llamadas"]
    assert not any(l[0] == "estado" for l in ent["llamadas"])  # no toca la campaña: no estaba 'pausado'


@pytest.mark.parametrize("estado", ["armando", "lanzando", "error"])
def test_ejecutar_activar_arroja_si_no_esta_en_meta(ent, estado):
    """M/brief: activar sobre un experimento que todavía no llegó a Meta
    (armando/lanzando/error) no es un no-op silencioso: lanza ValueError con
    el mensaje que la UI puede mostrar tal cual."""
    ac, ex, eid, ep = ent["ac"], ent["ex"], ent["eid"], ent["ep"]
    ex.actualizar("acme", eid, estado=estado)
    with pytest.raises(ValueError, match="El experimento todavía no está en Meta."):
        ac.ejecutar("acme", eid, "activar", {"ep_ids": [ep]})
    assert not any(l[0] == "activar" for l in ent["llamadas"])


def test_rescatar_idempotente_aunque_planificar_avance_el_escalon(ent, monkeypatch):
    """I1: cada pieza engendra a lo sumo un rescate por escalón. Simula lo
    que hará Task 5 (planificar sube escalon_rescate de la pieza) y verifica
    que una segunda llamada sobre el mismo escalón no vuelve a planificar ni
    a gastar, aunque la comparación ya no sea `==` sino `>=`."""
    ac, ex, eid, ep = ent["ac"], ent["ex"], ent["eid"], ent["ep"]

    def _planificar_y_subir_escalon(c, e, tipo, payload):
        ent["llamadas"].append(("planificar", tipo, payload.get("ep_id")))
        ex.actualizar_pieza(c, payload["ep_id"], escalon_rescate=1)
        return 99

    monkeypatch.setattr(ac.derivaciones, "planificar", _planificar_y_subir_escalon)
    ac.ejecutar("acme", eid, "rescatar", {"ep_id": ep})
    p = [p for p in ex.piezas("acme", eid) if p["id"] == ep][0]
    # `escalon_rescate` (columna) ya la subió el planificar (Task 5); la
    # marca de idempotencia se calcula sobre ese valor releído, no sobre el
    # que había antes de llamarlo.
    assert p["escalon_rescate"] == 1 and p["extra"]["rescatado_en_escalon"] == 2

    # Segunda llamada: el decisor vuelve a pedir el rescate sin que la pieza
    # haya avanzado más allá del escalón ya marcado -> no repite.
    ac.ejecutar("acme", eid, "rescatar", {"ep_id": ep})
    assert [l for l in ent["llamadas"] if l[0] == "planificar" and l[1] == "rescatar"] == \
        [("planificar", "rescatar", ep)]

    # Si la pieza avanza de escalón por otra vía, un nuevo rescate sí procede.
    ex.actualizar_pieza("acme", ep, escalon_rescate=2)
    ac.ejecutar("acme", eid, "rescatar", {"ep_id": ep})
    assert len([l for l in ent["llamadas"] if l[0] == "planificar" and l[1] == "rescatar"]) == 2


def test_rescatar_llama_planificar_antes_de_pausar(ent, monkeypatch):
    """I3: si planificar falla, la pieza no debe quedar pausada — pausar solo
    ocurre después de que el rescate exista."""
    ac, ex, eid, ep = ent["ac"], ent["ex"], ent["eid"], ent["ep"]

    def _falla(c, e, tipo, payload):
        raise RuntimeError("boom")

    monkeypatch.setattr(ac.derivaciones, "planificar", _falla)
    with pytest.raises(RuntimeError):
        ac.ejecutar("acme", eid, "rescatar", {"ep_id": ep})
    assert not any(l[0] == "pausar" for l in ent["llamadas"])


def test_marcar_pieza_no_pisa_extra_escrito_despues_del_read_inicial(ent):
    """I2: acciones.ejecutar lee `pz` al principio; si algo más escribe en
    `extra` de la misma pieza entre ese read y el marcado (p. ej.
    lanzador.activar_pieza guardando `activado_en`), marcar_pieza no debe
    perder ese dato."""
    ac, ex, eid, ep = ent["ac"], ent["ex"], ent["eid"], ent["ep"]
    pz_vieja = [p for p in ex.piezas("acme", eid) if p["id"] == ep][0]
    assert pz_vieja["extra"] == {}
    # Algo más (fuera de este ejecutar) escribe en extra después del read.
    ex.actualizar_pieza("acme", ep, extra={"activado_en": "2026-09-15T00:00:00"})
    ex.marcar_pieza("acme", ep, derivado=True)
    p = [p for p in ex.piezas("acme", eid) if p["id"] == ep][0]
    assert p["extra"] == {"activado_en": "2026-09-15T00:00:00", "derivado": True}


def test_pedir_registra_evento_error_y_relanza(ent, monkeypatch):
    """I3: pedir() no traga la excepción de ejecutar(); antes de relanzarla
    deja un evento tipo error, en español, con el token de Meta redactado."""
    ac, ex, eid, ep = ent["ac"], ent["ex"], ent["eid"], ent["ep"]

    def _falla(c, ep_):
        raise RuntimeError("Meta dijo: access_token=SECRETO123 inválido")

    monkeypatch.setattr(ac.lanzador, "pausar_pieza", _falla)
    with pytest.raises(RuntimeError):
        ac.pedir("acme", eid, "pausar", {"ep_id": ep}, "perdedor")
    eventos = ex.eventos("acme", eid)
    errores = [e for e in eventos if e["tipo"] == "error"]
    assert len(errores) == 1
    assert "access_token=***" in errores[0]["mensaje"]
    assert "SECRETO123" not in errores[0]["mensaje"]
    assert errores[0]["datos"]["accion"] == "pausar"
