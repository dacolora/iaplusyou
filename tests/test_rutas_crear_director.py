"""Rutas de Crear con el director (spec 2026-09-18 §7)."""
import pytest

from tests.test_rutas_experimentos import _cliente_admin


@pytest.fixture()
def app(base_temporal, monkeypatch, tmp_path):
    import dashboard
    import proyectos
    import referencias_flowplus
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    monkeypatch.setattr(dashboard.meta_conexion, "cargar", lambda c: {"moneda": "COP"})
    monkeypatch.setattr(dashboard.meta_conexion, "estado", lambda c: {"estado": "conectado", "verificado": True, "detalle": {}})
    monkeypatch.setattr(dashboard.trabajos, "en_curso", lambda job_id: False)
    monkeypatch.setattr(referencias_flowplus, "listar",
                        lambda c: [{"tipo": "imagen", "url": "https://x/1.png", "frame_url": "https://x/1.png", "etiqueta": "@Imagen 1"}])
    monkeypatch.setattr(referencias_flowplus, "vaciar", lambda c: None)
    encolados = []
    monkeypatch.setattr(dashboard.trabajos, "encolar",
                        lambda job_id, tipo, payload, **kw: (encolados.append({"job_id": job_id, "tipo": tipo, "payload": payload, **kw}), True)[1])
    return {"dashboard": dashboard, "c": _cliente_admin(dashboard), "encolados": encolados}


def test_settings_guarda_idioma_y_duracion_por_defecto(app):
    import proyectos
    r = app["c"].post("/cliente/acme/preferencias_flowplus/guardar", data={
        "modelo_video": "wan3", "modelo_imagen": "seedream_v5_pro", "idioma_prompt": "en", "duracion_defecto": "10"})
    assert r.status_code == 302
    p = proyectos.preferencias_flowplus("acme")
    assert p["idioma_prompt"] == "en" and p["duracion_defecto"] == 10
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert 'name="idioma_prompt"' in html and '<option value="en" selected>' in html
    assert 'name="duracion_defecto"' in html


def _crear(app, **extra):
    data = {"accion_central": "@Imagen 1 gira despacio", "duracion_objetivo": "8", "aspect_ratio": "9:16", "tipo": "video",
            "modelo": "wan3", "con_sonido": "si", "sonido": "brisa", "musica_estilo": ""}
    data.update(extra)
    return app["c"].post("/cliente/acme/creative_flow/crear", data=data)


def test_crear_no_genera_encola_el_director_y_deja_prompt_pendiente(app):
    import creative_flow as cf
    r = _crear(app)
    assert r.status_code == 302
    (cf_id, e), = cf.cargar("acme").items()
    assert e["estado"] == "prompt_pendiente" and e["prompt_relleno"] is None
    assert e["prompt_fuente"] == "@Imagen 1 gira despacio" and e["calidad"] == "final" and e["idioma_prompt"] == "es"
    assert e["referencias"][0]["token"] == "Image 1" and e["preset_camara"] is None and e["plantilla"] is None
    assert [t["tipo"] for t in app["encolados"]] == ["flowplus_director"]
    t = app["encolados"][0]
    assert t["job_id"] == f"acme__{cf_id}__director" and t["payload"] == {"cliente": "acme", "cf_id": cf_id, "auto_lanzar": False, "prioridad": 5}
    assert t["max_intentos"] == 2


def test_crear_borrador_solo_en_wan_y_logos_como_image_k(app, monkeypatch):
    import creative_flow as cf
    monkeypatch.setattr(app["dashboard"], "_logos", lambda c: [{"url": "https://x/logo.png"}])
    _crear(app, calidad="borrador")
    _crear(app, calidad="borrador", modelo="kling_o3_pro", duracion_objetivo="8")
    items = sorted(cf.cargar("acme").values(), key=lambda e: e["creado_en"])
    assert items[0]["calidad"] == "borrador" and items[1]["calidad"] == "final"
    assert [r["token"] for r in items[0]["referencias"]] == ["Image 1", "Image 2"] and items[0]["referencias"][1]["logo"] is True


def test_guardar_prompt_solo_en_prompt_listo(app):
    import creative_flow as cf
    _crear(app)
    (cf_id, _), = cf.cargar("acme").items()
    r = app["c"].post(f"/cliente/acme/creative_flow/{cf_id}/prompt", data={"prompt_a": "NUEVO A", "prompt_b": "NUEVO B"})
    assert r.status_code == 302 and cf.cargar("acme")[cf_id]["prompt_relleno"] is None      # aún pendiente: no se guarda
    cf.actualizar("acme", cf_id, estado="prompt_listo", prompt_relleno="A", director={"estado": "ok", "prompt_b": "B"})
    app["c"].post(f"/cliente/acme/creative_flow/{cf_id}/prompt", data={"prompt_a": "  NUEVO A ", "prompt_b": "NUEVO B"})
    e = cf.cargar("acme")[cf_id]
    assert e["prompt_relleno"] == "NUEVO A" and e["director"]["prompt_b"] == "NUEVO B" and e["director"]["editado_en"]
    # vacío no pisa
    app["c"].post(f"/cliente/acme/creative_flow/{cf_id}/prompt", data={"prompt_a": "   "})
    assert cf.cargar("acme")[cf_id]["prompt_relleno"] == "NUEVO A"


def test_rearmar_vuelve_a_pendiente_y_encola(app):
    import creative_flow as cf
    _crear(app)
    (cf_id, _), = cf.cargar("acme").items()
    cf.actualizar("acme", cf_id, estado="prompt_listo", prompt_relleno="A")
    app["encolados"].clear()
    r = app["c"].post(f"/cliente/acme/creative_flow/{cf_id}/rearmar")
    assert r.status_code == 302 and cf.cargar("acme")[cf_id]["estado"] == "prompt_pendiente"
    assert app["encolados"][0]["tipo"] == "flowplus_director" and app["encolados"][0]["payload"]["auto_lanzar"] is False
    cf.actualizar("acme", cf_id, estado="video_listo")
    app["encolados"].clear()
    app["c"].post(f"/cliente/acme/creative_flow/{cf_id}/rearmar")
    assert app["encolados"] == []


def test_rearmar_nunca_una_imagen_aunque_este_en_prompt_listo(app):
    """Guarda que la condición de tipo en cf_rearmar hace algo por sí sola: una
    imagen en prompt_listo (no ocurre en la práctica: imagen nunca pasa por el
    director) igual debe rechazarse, no solo por el estado."""
    import creative_flow as cf
    _crear(app, tipo="imagen", modelo="seedream_v5_pro")
    (cf_id, _), = cf.cargar("acme").items()
    cf.actualizar("acme", cf_id, estado="prompt_listo")
    app["encolados"].clear()
    r = app["c"].post(f"/cliente/acme/creative_flow/{cf_id}/rearmar")
    assert r.status_code == 302 and app["encolados"] == []
    assert cf.cargar("acme")[cf_id]["estado"] == "prompt_listo"


def test_items_traen_trabajo_del_director_y_costo_con_calidad(app, monkeypatch):
    import creative_flow as cf
    _crear(app, calidad="borrador")
    (cf_id, _), = cf.cargar("acme").items()
    monkeypatch.setattr(app["dashboard"].trabajos, "en_curso", lambda job_id: job_id.endswith("__director"))
    item = app["dashboard"]._creative_flow_items("acme")[0]
    assert item["trabajo_director"] == {"job_id": f"acme__{cf_id}__director"}
    cf.actualizar("acme", cf_id, estado="prompt_listo", prompt_relleno="A")
    item = app["dashboard"]._creative_flow_items("acme")[0]
    assert item["costo_estimado"]["usd"] == 0.4      # 8 s x 0,05 (480p)
