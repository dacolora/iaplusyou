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


def _lista(app):
    import creative_flow as cf
    _crear(app)
    (cf_id, _), = cf.cargar("acme").items()
    cf.actualizar("acme", cf_id, estado="prompt_listo", prompt_relleno="A", director={"estado": "ok", "prompt_b": "B", "diferencia_b": "otro"})
    app["encolados"].clear()
    return cf_id


def test_generar_solo_a(app):
    import creative_flow as cf
    cf_id = _lista(app)
    r = app["c"].post(f"/cliente/acme/creative_flow/{cf_id}/generar_video")
    assert r.status_code == 302
    assert [t["tipo"] for t in app["encolados"]] == ["flowplus_video"] and app["encolados"][0]["payload"]["cf_id"] == cf_id
    assert len(cf.cargar("acme")) == 1
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert "Generando el video con Wan 3.0" in html


def test_generar_a_y_b_crea_la_hija_y_encola_dos(app):
    import creative_flow as cf
    cf_id = _lista(app)
    app["c"].post(f"/cliente/acme/creative_flow/{cf_id}/generar_video", data={"version_b": "si"})
    sesiones = cf.cargar("acme")
    assert len(sesiones) == 2
    hija = next(e for k, e in sesiones.items() if k != cf_id)
    assert hija["variante"] == "B" and hija["prompt_relleno"] == "B" and hija["derivado_de"] == cf_id
    assert sorted(t["payload"]["cf_id"] for t in app["encolados"]) == sorted(sesiones)
    assert all(t["tipo"] == "flowplus_video" for t in app["encolados"])


def test_generar_b_sin_prompt_b_ignora_la_casilla(app):
    import creative_flow as cf
    cf_id = _lista(app)
    cf.actualizar("acme", cf_id, director={"estado": "fallback", "prompt_b": None})
    app["c"].post(f"/cliente/acme/creative_flow/{cf_id}/generar_video", data={"version_b": "si"})
    assert len(cf.cargar("acme")) == 1 and len(app["encolados"]) == 1


def test_reusar_precarga_sonido_musica_y_calidad(app):
    import creative_flow as cf
    cf_id = _lista(app)
    cf.actualizar("acme", cf_id, sonido_texto="brisa", musica_estilo="lujo", calidad="borrador")
    with app["c"].session_transaction() as s:
        s["fp_prefill"] = None
    app["c"].post(f"/cliente/acme/flowplus/reusar/{cf_id}")
    with app["c"].session_transaction() as s:
        p = s["fp_prefill"]
    assert p["texto"] == "@Imagen 1 gira despacio" and p["con_sonido"] is True and p["sonido_texto"] == "brisa"
    assert p["musica_estilo"] == "lujo" and p["calidad"] == "borrador" and p["preset_camara"] is None and p["plantilla"] is None


def test_formulario_trae_armar_prompt_borrador_y_duracion_de_la_preferencia(app):
    import proyectos
    proyectos.guardar_preferencias_flowplus("acme", "wan3", "seedream_v5_pro", idioma_prompt="es", duracion_defecto=8)
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert "Armar prompt (gratis)" in html and 'id="fp-calidad"' in html and 'name="calidad" value="borrador"' in html
    assert '<option value="8" selected>8 s</option>' in html and 'id="fp-duracion-larga"' in html
    assert "exactamente lo que recibe el modelo" not in html
    # La imagen se cobra al instante (nunca pasa por el director): su botón en
    # refrescar() debe seguir diciendo "Generar imagen", nunca "gratis".
    assert "'Generar imagen'" in html
    # El costo A+B se delega sobre el cuerpo del modal (el formulario de generar
    # vive en el <template> clonado, igual que "Producir N finales"): un
    # querySelectorAll('.fp-generar-form') en la carga de la página nunca vería
    # el checkbox, así que ese patrón no puede volver.
    assert "'.fp-version-b'" in html
    assert "querySelectorAll('.fp-generar-form')" not in html


def test_tarjeta_pendiente_muestra_la_barra_del_director(app, monkeypatch):
    import creative_flow as cf
    _crear(app)
    (cf_id, _), = cf.cargar("acme").items()
    monkeypatch.setattr(app["dashboard"].trabajos, "en_curso", lambda job_id: job_id.endswith("__director"))
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert f'id="trabajo-acme__{cf_id}__director"' in html and "Armando el prompt" in html


def test_tarjeta_lista_trae_el_editor_rearmar_y_version_b(app):
    import creative_flow as cf
    cf_id = _lista(app)
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert f'action="/cliente/acme/creative_flow/{cf_id}/prompt"' in html and 'name="prompt_a"' in html and 'name="prompt_b"' in html
    assert f'action="/cliente/acme/creative_flow/{cf_id}/rearmar"' in html
    assert 'name="version_b" value="si"' in html and "otro" in html      # diferencia_b visible
    assert "Generar (~$0.8)" in html or "Generar (~$0.80)" in html          # 8 s x 0,10
    cf.actualizar("acme", cf_id, director={"estado": "fallback", "aviso": "Anthropic caído", "prompt_b": None})
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert "no pudo armar los planos" in html and "Anthropic caído" in html and 'name="version_b"' not in html


def test_tarjeta_de_la_hija_muestra_version_b(app):
    import creative_flow as cf
    cf_id = _lista(app)
    hija = cf.duplicar("acme", cf_id, prompt_relleno="B", variante="B")
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert "Versión B" in html and "Versión A" in html


def test_version_b_checkbox_se_oculta_si_ya_existe_hija(app):
    """Decisión de controlador: si la sesión ya tiene una hija de versión B,
    no tiene sentido ofrecer generarla de nuevo — se oculta la casilla."""
    import creative_flow as cf
    cf_id = _lista(app)
    cf.duplicar("acme", cf_id, prompt_relleno="B", variante="B")
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert 'name="version_b"' not in html
