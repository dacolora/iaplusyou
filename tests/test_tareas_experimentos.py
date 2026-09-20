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


# --- Piezas de imagen: sin orgánico, sin rescate ni derivación ---------------

def _experimento_activo(ex, pid, modo="auto"):
    eid = ex.crear("acme", "X", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP", modo=modo)
    ex.actualizar("acme", eid, estado="corriendo", meta_campaign_id="c1")
    ep = ex.agregar_pieza("acme", eid, pid, "CO")
    ex.actualizar_pieza("acme", ep, meta_ad_id=f"ad{ep}", estado="activo")
    return eid, ep


def _decisor_fijo(monkeypatch, te, veredicto, accion):
    monkeypatch.setattr(te.decisor, "decidir", lambda snaps, reglas, ctx: {
        "veredicto": veredicto, "motivo": "m", "accion": accion, "puerta": 1, "numeros": {}})


def _pedidas(monkeypatch, te):
    """acciones.pedir falso: anota qué acción se pidió y dice que se ejecutó."""
    pedidas = []
    monkeypatch.setattr(te.acciones, "pedir",
                        lambda c, e, accion, payload, motivo: (pedidas.append(accion), ("ejecutada", "ok"))[1])
    return pedidas


def test_ganadora_imagen_en_auto_no_publica_organico_ni_redacta(base_temporal, monkeypatch):
    """F1: organico/publicador son solo de video (una PNG se bajaría como .mp4
    y se subiría como Reel). Una imagen ganadora en modo auto, con canales
    conectados, no encola organico_publicar ni llama a Claude a redactar."""
    import cola
    import experimentos as ex
    import organico
    import tareas
    from tareas import experimentos as te
    from tests.test_experimentos_db import _pieza_imagen
    tareas.cargar_todas()
    pid = _pieza_imagen(base_temporal)
    eid, ep = _experimento_activo(ex, pid, modo="auto")
    _decisor_fijo(monkeypatch, te, "ganador", "escalar_y_derivar")
    monkeypatch.setattr(organico, "disponibles", lambda c: ["instagram", "facebook"])
    redactadas = []
    monkeypatch.setattr(organico, "redactar", lambda c, p, plats: (redactadas.append(list(plats)), {
        x: {"titulo": f"T {x}", "caption": f"Texto {x}", "extra": {}} for x in plats})[1])
    monkeypatch.setattr(te.acciones.lanzador, "escalar_pais", lambda *a, **k: 30.0)
    monkeypatch.setattr(te.acciones.derivaciones, "planificar", lambda *a, **k: 99)
    te.exp_decidir({"payload": {"cliente": "acme", "experimento_id": eid}})
    assert cola.consultar_por_job(f"acme__pieza{pid}__organico") is None
    assert redactadas == [] and organico.listar("acme", pieza_id=pid) == []
    acciones_pedidas = [e["datos"].get("accion") for e in ex.eventos("acme", eid) if e["tipo"] in ("accion", "propuesta")]
    assert "publicar_organico" not in acciones_pedidas


def test_perdedora_imagen_pide_pausar_y_no_rescatar(base_temporal, monkeypatch):
    """F2: derivaciones rechaza sesiones de imagen; el rescate se cambia por
    una pausa y queda un evento que lo explica."""
    import experimentos as ex
    import tareas
    from tareas import experimentos as te
    from tests.test_experimentos_db import _pieza_imagen
    tareas.cargar_todas()
    pid = _pieza_imagen(base_temporal)
    eid, ep = _experimento_activo(ex, pid)
    _decisor_fijo(monkeypatch, te, "perdedor", "rescatar")
    pedidas = _pedidas(monkeypatch, te)
    te.exp_decidir({"payload": {"cliente": "acme", "experimento_id": eid}})
    assert pedidas == ["pausar"]
    assert any("sin rescate/derivación" in e["mensaje"] for e in ex.eventos("acme", eid))


def test_ganadora_imagen_escala_y_no_deriva(base_temporal, monkeypatch):
    import experimentos as ex
    import organico
    import tareas
    from tareas import experimentos as te
    from tests.test_experimentos_db import _pieza_imagen
    tareas.cargar_todas()
    pid = _pieza_imagen(base_temporal)
    eid, ep = _experimento_activo(ex, pid)
    _decisor_fijo(monkeypatch, te, "ganador", "escalar_y_derivar")
    monkeypatch.setattr(organico, "disponibles", lambda c: ["instagram"])
    pedidas = _pedidas(monkeypatch, te)
    te.exp_decidir({"payload": {"cliente": "acme", "experimento_id": eid}})
    assert pedidas == ["escalar"]
    assert any("sin rescate/derivación" in e["mensaje"] for e in ex.eventos("acme", eid))


def test_video_sigue_pidiendo_rescate_derivacion_y_organico(base_temporal, monkeypatch):
    import experimentos as ex
    import organico
    import tareas
    from tareas import experimentos as te
    from tests.test_experimentos_db import _pieza
    tareas.cargar_todas()
    monkeypatch.setattr(organico, "disponibles", lambda c: ["instagram"])
    pedidas = _pedidas(monkeypatch, te)

    eid, ep = _experimento_activo(ex, _pieza(base_temporal))
    _decisor_fijo(monkeypatch, te, "perdedor", "rescatar")
    te.exp_decidir({"payload": {"cliente": "acme", "experimento_id": eid}})
    assert pedidas == ["pausar", "rescatar"]

    del pedidas[:]
    eid2, ep2 = _experimento_activo(ex, _pieza(base_temporal, legado="cf_9__es_CO"))
    _decisor_fijo(monkeypatch, te, "ganador", "escalar_y_derivar")
    te.exp_decidir({"payload": {"cliente": "acme", "experimento_id": eid2}})
    assert pedidas == ["escalar", "derivar", "publicar_organico"]
    assert not any("sin rescate/derivación" in e["mensaje"] for e in ex.eventos("acme", eid) + ex.eventos("acme", eid2))
