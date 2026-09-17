def test_job_id_y_lanzar_encolan_con_prioridad(base_temporal, monkeypatch):
    import creative_flow
    import flowplus_lanzar
    import trabajos
    cf_id = creative_flow.crear("acme", [], ["Espejo LED"], [], "gira", 8, "", "A", referencias_urls=["https://r2/a.jpg"])
    creative_flow.actualizar("acme", cf_id, prompt_relleno="P", tipo="imagen", modelo="seedream_v5_pro")
    encolados = []
    monkeypatch.setattr(trabajos, "encolar", lambda job_id, tipo, payload, **kw: encolados.append((job_id, tipo, payload, kw)) or True)
    entry = creative_flow.cargar("acme")[cf_id]
    assert flowplus_lanzar.job_id("acme", cf_id) == f"acme__{cf_id}__creative_flow"
    assert flowplus_lanzar.lanzar("acme", cf_id, entry, prioridad=3) is True
    job_id, tipo, payload, kw = encolados[0]
    assert tipo == "flowplus_imagen" and payload == {"cliente": "acme", "cf_id": cf_id}
    assert kw["max_intentos"] == 1 and kw["prioridad"] == 3 and kw["duracion_estimada"] == 60 and kw["cliente"] == "acme"
    assert creative_flow.cargar("acme")[cf_id]["estado"] == "video_generando"
    creative_flow.actualizar("acme", cf_id, tipo="video")
    flowplus_lanzar.lanzar("acme", cf_id, creative_flow.cargar("acme")[cf_id])
    assert encolados[1][1] == "flowplus_video" and encolados[1][3]["prioridad"] == 5 and encolados[1][3]["duracion_estimada"] == 180


def test_dashboard_delega_en_flowplus_lanzar(base_temporal, monkeypatch):
    import dashboard
    import flowplus_lanzar
    llamadas = []
    monkeypatch.setattr(flowplus_lanzar, "lanzar", lambda c, cf, e, prioridad=5: llamadas.append((c, cf, prioridad)) or True)
    assert dashboard._job_id_creative_flow("acme", "cf_1") == flowplus_lanzar.job_id("acme", "cf_1")
    assert dashboard._lanzar_video_cf("acme", "cf_1", {"tipo": "video"}) is True
    assert llamadas == [("acme", "cf_1", 5)]
