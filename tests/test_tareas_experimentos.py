import pytest

from tests.test_experimentos_db import PAISES


def test_job_ids():
    from tareas import experimentos as te
    assert te.job_id_lanzar("acme", 3) == "acme__exp3__lanzar"
    assert te.job_id_refrescar("acme", 3) == "acme__exp3__refrescar"


def test_exp_lanzar_llama_lanzador_y_reporta(base_temporal, monkeypatch):
    import tareas
    import trabajos
    from tareas import experimentos as te
    llamadas = []
    monkeypatch.setattr(te.lanzador, "lanzar", lambda c, e, on_etapa=None: (on_etapa("Campaña"), llamadas.append((c, e)), "ok")[-1])
    reportes = []
    monkeypatch.setattr(trabajos, "reportar", lambda job_id, **kw: reportes.append((job_id, kw)))
    tareas.cargar_todas()
    fn = tareas.REGISTRO["exp_lanzar"]
    assert fn({"payload": {"cliente": "acme", "experimento_id": 3}, "job_id": "acme__exp3__lanzar"}) == "ok"
    assert llamadas == [("acme", 3)] and reportes[0][1]["etapa"] == "Campaña"


def test_exp_lanzar_interrumpida_marca_error(base_temporal):
    import experimentos as ex
    import tareas
    tareas.cargar_todas()
    eid = ex.crear("acme", "X", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ex.actualizar("acme", eid, estado="lanzando")
    tareas.AL_INTERRUMPIR["exp_lanzar"]({"payload": {"cliente": "acme", "experimento_id": eid}}, "se cayó")
    e = ex.obtener("acme", eid)
    assert e["estado"] == "error" and "se cayó" in e["error"]
    ex.actualizar("acme", eid, estado="pausado", error=None)
    tareas.AL_INTERRUMPIR["exp_lanzar"]({"payload": {"cliente": "acme", "experimento_id": eid}}, "otra")
    assert ex.obtener("acme", eid)["estado"] == "pausado"  # no pisa estados finales


def test_exp_refrescar_todos_encola_los_corriendo(base_temporal, monkeypatch):
    import cola
    import experimentos as ex
    import tareas
    tareas.cargar_todas()
    e1 = ex.crear("acme", "A", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    e2 = ex.crear("acme", "B", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    e3 = ex.crear("otro", "C", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ex.actualizar("acme", e1, estado="corriendo")
    ex.actualizar("otro", e3, estado="corriendo")
    encolados = []
    monkeypatch.setattr(cola, "encolar", lambda tipo, payload, **kw: encolados.append((tipo, payload, kw.get("job_id"))))
    tareas.REGISTRO["exp_refrescar_todos"]({"payload": {}})
    assert sorted(x[1]["experimento_id"] for x in encolados) == sorted([e1, e3])
    assert all(x[0] == "exp_refrescar" for x in encolados)


def test_ctx_lleva_es_imagen_segun_la_pieza(base_temporal, monkeypatch):
    import experimentos as ex
    import tareas
    from tareas import experimentos as te
    from tests.test_experimentos_db import _pieza, _pieza_imagen
    tareas.cargar_todas()
    contextos = []

    def fake_decidir(snaps, reglas, contexto):
        contextos.append(contexto)
        return {"veredicto": "pendiente", "motivo": "", "accion": None, "puerta": 0, "numeros": {}}
    monkeypatch.setattr(te.decisor, "decidir", fake_decidir)

    def _decidir_con(pid):
        eid = ex.crear("acme", "X", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
        ex.actualizar("acme", eid, estado="corriendo")
        ep = ex.agregar_pieza("acme", eid, pid, "CO")
        ex.actualizar_pieza("acme", ep, meta_ad_id=f"ad{ep}", estado="activo")
        te.exp_decidir({"payload": {"cliente": "acme", "experimento_id": eid}})

    _decidir_con(_pieza(base_temporal))
    _decidir_con(_pieza_imagen(base_temporal))

    assert len(contextos) == 2
    assert contextos[0]["es_imagen"] is False
    assert contextos[1]["es_imagen"] is True


def test_periodica_registrada():
    import worker
    assert ("exp_refrescar_todos", 7200) in worker.PERIODICAS
