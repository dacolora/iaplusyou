"""Derivar y rescatar no aplican a experimentos de instalaciones de la app
(spec 2026-10-07): cada pieza tiene una fila por plataforma y una pieza
derivada nacería sin plataforma. Pausar, escalar y archivar siguen igual."""
import pytest

from tests.test_experimentos_db import PAISES, _pieza


def _armar(base_temporal, monkeypatch, objetivo, modo="auto"):
    import acciones
    import experimentos as ex
    llamadas = []
    monkeypatch.setattr(acciones.lanzador, "pausar_pieza", lambda c, ep: llamadas.append(("pausar", ep)))
    monkeypatch.setattr(acciones.lanzador, "escalar_pais",
                        lambda c, e, p, pct, tope_dia=None: (llamadas.append(("escalar", p)), 24.0)[1])
    monkeypatch.setattr(acciones.derivaciones, "planificar",
                        lambda c, e, tipo, payload: (llamadas.append(("planificar", tipo)), 99)[1])
    pid = _pieza(base_temporal)
    if objetivo == "OUTCOME_APP_PROMOTION":
        # Las filas de apps (una por tienda) solo las arma crear_con_piezas: agregar_pieza las rechaza.
        datos = dict(nombre="X", paises=[p for p in PAISES if p["pais"] == "CO"], objetivo_meta=objetivo, dias=7,
                     tope_total=100.0, destino_url="https://apps.apple.com/co/app/x/id1", moneda="COP", modo=modo,
                     app={"ios_url": "https://apps.apple.com/co/app/x/id1"})
        eid = ex.crear_con_piezas("acme", datos, [(pid, "CO")])
        ep = ex.piezas("acme", eid)[0]["id"]
    else:
        eid = ex.crear("acme", "X", PAISES, objetivo, 7, 100.0, "https://t", "COP", modo=modo)
        ep = ex.agregar_pieza("acme", eid, pid, "CO")
    ex.actualizar_pieza("acme", ep, meta_ad_id="ad1", estado="activo")
    ex.actualizar("acme", eid, estado="corriendo", meta_campaign_id="c1")
    return acciones, ex, eid, ep, llamadas


@pytest.mark.parametrize("accion", ["derivar", "rescatar"])
@pytest.mark.parametrize("modo", ["manual", "semi", "auto"])
def test_apps_no_deriva_ni_rescata(base_temporal, monkeypatch, accion, modo):
    import propuestas
    ac, ex, eid, ep, llamadas = _armar(base_temporal, monkeypatch, "OUTCOME_APP_PROMOTION", modo)
    estado, msg = ac.pedir("acme", eid, accion, {"ep_id": ep}, "perdedor")
    assert estado == "omitida" and "instalaciones de la app" in msg
    assert propuestas.pendientes("acme", eid) == []
    assert not any(l[0] == "planificar" for l in llamadas)
    eventos = [e for e in ex.eventos("acme", eid) if "instalaciones" in e["mensaje"]]
    assert len(eventos) == 1
    pz = [p for p in ex.piezas("acme", eid) if p["id"] == ep][0]
    assert not (pz.get("extra") or {}).get("derivado")


def test_apps_escalar_y_pausar_siguen_funcionando(base_temporal, monkeypatch):
    ac, ex, eid, ep, llamadas = _armar(base_temporal, monkeypatch, "OUTCOME_APP_PROMOTION", "auto")
    assert ac.pedir("acme", eid, "escalar", {"pais": "CO", "ep_id": ep}, "ganador")[0] == "ejecutada"
    assert ac.pedir("acme", eid, "pausar", {"ep_id": ep}, "perdedor")[0] == "ejecutada"
    assert ("escalar", "CO") in llamadas and ("pausar", ep) in llamadas


@pytest.mark.parametrize("modo,esperado", [("auto", "ejecutada"), ("manual", "propuesta")])
def test_apps_perdedor_termina_pausado_no_atascado(base_temporal, monkeypatch, modo, esperado):
    """El decisor pide `pausar` y luego `rescatar`; el rescate se omite y la
    pausa queda ejecutada (auto) o propuesta (manual)."""
    import propuestas
    from tareas import experimentos as te
    ac, ex, eid, ep, llamadas = _armar(base_temporal, monkeypatch, "OUTCOME_APP_PROMOTION", modo)
    monkeypatch.setattr(te, "_diagnosticar", lambda *a, **k: None)
    monkeypatch.setattr(te, "_aprender", lambda *a, **k: None)
    exp = ac._experimento("acme", eid)
    pz = [p for p in exp["piezas"] if p["id"] == ep][0]
    resultado = {"veredictos": [], "ganadores": [], "propuestas": [], "errores": [], "escalados": set(),
                 "organico_propuesto": set()}
    v = {"veredicto": "perdedor", "motivo": "x", "accion": "rescatar", "puerta": 1, "numeros": {}}
    te._aplicar_veredicto("acme", exp, pz, v, resultado)
    assert resultado["errores"] == []
    if esperado == "ejecutada":
        assert ("pausar", ep) in llamadas
    else:
        assert [p["accion"] for p in propuestas.pendientes("acme", eid)] == ["pausar"]
    assert not any(l[0] == "planificar" for l in llamadas)
    assert "rescatar" not in [p["accion"] for p in propuestas.pendientes("acme", eid)]


def test_traffic_sigue_proponiendo_derivar_y_rescatar(base_temporal, monkeypatch):
    import propuestas
    ac, ex, eid, ep, llamadas = _armar(base_temporal, monkeypatch, "OUTCOME_TRAFFIC", "semi")
    monkeypatch.setattr(ac, "_precio_estimado", lambda *a, **k: {"usd": None, "texto": "precio no disponible"})
    assert ac.pedir("acme", eid, "derivar", {"ep_id": ep}, "ganador")[0] == "propuesta"
    assert ac.pedir("acme", eid, "rescatar", {"ep_id": ep}, "perdedor")[0] == "propuesta"
    assert sorted(p["accion"] for p in propuestas.pendientes("acme", eid)) == ["derivar", "rescatar"]
