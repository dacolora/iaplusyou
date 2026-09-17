import pytest


@pytest.fixture()
def escenario(base_temporal, monkeypatch):
    import catalogo_productos, marca, proyectos
    from sprints import datos
    from storage import r2_uploader
    monkeypatch.setattr(marca, "guia_efectiva", lambda c: "Luz natural.")
    monkeypatch.setattr(marca, "negative_prompt_efectivo", lambda c: None)
    monkeypatch.setattr(catalogo_productos, "encontrar", lambda c, pid, categoria=None: {
        "id": "espejo_led", "nombre": "Espejo LED", "descripcion": "redondo", "regla": "Idéntico.", "categoria": "producto",
        "referencias": ["/tmp/espejo/1.jpg", "/tmp/espejo/2.jpg"], "imagenes": ["1.jpg", "2.jpg"]})
    monkeypatch.setattr(r2_uploader, "upload_image", lambda ruta, key: f"https://r2/{key}")
    monkeypatch.setattr(proyectos, "preferencias_flowplus", lambda c: {"modelo_video": "wan3", "modelo_imagen": "seedream_v5_pro"})
    monkeypatch.setattr(proyectos, "nombre_visible", lambda c: "Vidrios Sol")
    pid = datos.crear_persona("acme", "Premium", resumen="Busca calidad", tono="cercano", senales_visuales=["cocina"])
    tid = datos.crear_temporada("acme", "Navidad", "2026-11-15", "2026-12-31", contexto="regalos")
    sid = datos.crear_sprint("acme", "Sprint octubre", "2026-10-01", "2026-10-31", destinos=["es_CO", "en_US"])
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 2, 1)
    r1 = datos.agregar_referencia("acme", cid, "imagen", "https://r2/ref1.jpg", descripcion="luz")
    r2 = datos.agregar_referencia("acme", cid, "video", "https://r2/ref2.mp4", frame_url="https://r2/ref2.frame.jpg", descripcion="mov")
    iv = datos.crear_idea("acme", cid, "video", "Amanecer", "Rodea el espejo", sonido="pájaros", enfoque="producto",
                          gancho="Luz", referencias_ids=[r2], duracion_s=8, plataformas=["instagram"], estado_idea="aprobada")
    ii = datos.crear_idea("acme", cid, "imagen", "Marco", "Primer plano", enfoque="producto", estado_idea="aprobada")
    ip = datos.crear_idea("acme", cid, "video", "Sin aprobar", "x", estado_idea="propuesta")
    return {"sid": sid, "cid": cid, "iv": iv, "ii": ii, "ip": ip, "r1": r1, "r2": r2}


def test_estimar_cuenta_aprobadas_sin_sesion(escenario):
    from sprints import produccion
    from providers import flowplus_modelos
    e = produccion.estimar("acme", escenario["sid"])
    assert e["videos"] == 1 and e["imagenes"] == 1 and e["segundos"] == 180 + 60
    esperado = flowplus_modelos.estimate_video("wan3", 8)["usd"] + flowplus_modelos.estimate_imagen("seedream_v5_pro", 3)["usd"]
    assert abs(e["usd"] - esperado) < 1e-6 and e["modelo_video"] == "wan3" and "USD" in e["texto"]
    e2 = produccion.estimar("acme", escenario["sid"], modelo_video="kling_o3_pro")
    assert e2["modelo_video"] == "kling_o3_pro" and e2["usd"] > e["usd"]
    assert produccion.estimar("acme", escenario["sid"], modelo_video="inventado")["modelo_video"] == "wan3"


def test_crear_sesion_arma_referencias_prompt_y_vinculo(escenario):
    import creative_flow
    from sprints import datos, produccion
    sp = datos.sprint("acme", escenario["sid"])
    c = sp["campanas"][0]
    idea = datos.idea("acme", escenario["iv"])
    refs, urls, productos = produccion.referencias_sesion("acme", c, idea)
    assert productos == ["Espejo LED"]
    assert refs[0]["etiqueta"] == "@Producto 1" and refs[0]["producto"] == "Espejo LED" and refs[0]["regla"] == "Idéntico."
    # la referencia de la idea (r2, video) va antes que la otra (r1)
    assert [r["url"] for r in refs[1:3]] == ["https://r2/ref2.mp4", "https://r2/ref1.jpg"]
    assert refs[1]["tipo"] == "video" and refs[1]["frame_url"] == "https://r2/ref2.frame.jpg" and refs[1]["etiqueta"] == "@Video 1"
    assert refs[2]["etiqueta"] == "@Imagen 1" and urls[1] == "https://r2/ref2.frame.jpg"
    cf_id = produccion.crear_sesion("acme", sp, c, idea, "wan3", "seedream_v5_pro")
    e = creative_flow.cargar("acme")[cf_id]
    assert e["sprint"] == {"sprint_id": sp["id"], "sprint_nombre": "Sprint octubre", "campana_id": c["id"], "campana_n": 1, "cp_id": idea["id"]}
    assert e["tipo"] == "video" and e["modelo"] == "wan3" and e["duracion_objetivo"] == 8 and e["tono"] == "cercano"
    assert e["platforms"] == ["instagram"] and e["aspect_ratio"] == "9:16" and e["enfoque"] == "producto"
    assert "AUDIENCIA: Busca calidad" in e["prompt_relleno"] and "TEMPORADA: Navidad" in e["prompt_relleno"]
    assert "SONIDO: pájaros" in e["prompt_relleno"] and "ESCENA: Rodea el espejo" in e["prompt_relleno"]
    assert datos.idea("acme", escenario["iv"])["cf_id"] == cf_id
    idea_img = datos.idea("acme", escenario["ii"])
    cf2 = produccion.crear_sesion("acme", sp, c, idea_img, "wan3", "seedream_v5_pro")
    e2 = creative_flow.cargar("acme")[cf2]
    assert e2["tipo"] == "imagen" and e2["modelo"] == "seedream_v5_pro" and "SONIDO" not in e2["prompt_relleno"]


def test_lanzar_lote_encola_con_prioridad_y_registra(escenario, monkeypatch):
    import flowplus_lanzar
    from sprints import datos, produccion
    lanzados = []
    monkeypatch.setattr(flowplus_lanzar, "lanzar", lambda c, cf, e, prioridad=5: lanzados.append((cf, e["tipo"], prioridad)) or True)
    r = produccion.lanzar_lote("acme", escenario["sid"])
    assert r["encoladas"] == 2 and r["omitidas"] == 0 and len(r["cf_ids"]) == 2 and r["usd"] > 0
    assert sorted(t for _, t, _ in lanzados) == ["imagen", "video"] and all(p == 3 for _, _, p in lanzados)
    sp = datos.sprint("acme", escenario["sid"])
    assert sp["extra"]["lote_en_curso"] is True and abs(sp["extra"]["costo_estimado_usd"] - r["usd"]) < 1e-6
    assert sp["eventos"][0]["tipo"] == "lote_encolado" and sp["eventos"][0]["datos"]["encoladas"] == 2
    assert datos.idea("acme", escenario["ip"])["cf_id"] is None      # la propuesta no se genera
    r2 = produccion.lanzar_lote("acme", escenario["sid"])
    assert r2["encoladas"] == 0                                        # idempotente: ya tienen sesión
    with pytest.raises(datos.ErrorDatos):
        produccion.lanzar_lote("acme", 999)


def test_reintentar_y_regenerar(escenario, monkeypatch):
    import creative_flow
    import flowplus_lanzar
    from sprints import datos, produccion
    lanzados = []
    monkeypatch.setattr(flowplus_lanzar, "lanzar", lambda c, cf, e, prioridad=5: lanzados.append(cf) or True)
    produccion.lanzar_lote("acme", escenario["sid"], campana_id=escenario["cid"])
    cf = datos.idea("acme", escenario["iv"])["cf_id"]
    assert produccion.reintentar("acme", escenario["iv"]) is False       # no está en error
    creative_flow.actualizar("acme", cf, estado="error", error="timeout")
    assert produccion.reintentar("acme", escenario["iv"]) is True and lanzados[-1] == cf
    creative_flow.actualizar("acme", cf, estado="video_listo", video_url="https://r2/v.mp4")
    datos.actualizar_idea("acme", escenario["iv"], qa={"score": 40}, revision="rechazada", revision_motivo="feo")
    nuevo = produccion.regenerar("acme", escenario["iv"])
    assert nuevo != cf and lanzados[-1] == nuevo
    i = datos.idea("acme", escenario["iv"])
    assert i["cf_id"] == nuevo and i["qa"] is None and i["revision"] == "pendiente" and i["revision_motivo"] is None
    assert creative_flow.cargar("acme")[nuevo]["sprint"]["cp_id"] == escenario["iv"]
    assert i["extra"]["cf_anteriores"] == [cf]


def test_progreso_agregado(escenario, monkeypatch):
    import cola
    import creative_flow
    import flowplus_lanzar
    from sprints import datos, produccion
    monkeypatch.setattr(flowplus_lanzar, "lanzar", lambda c, cf, e, prioridad=5: True)
    produccion.lanzar_lote("acme", escenario["sid"])
    cfv, cfi = datos.idea("acme", escenario["iv"])["cf_id"], datos.idea("acme", escenario["ii"])["cf_id"]
    monkeypatch.setattr(cola, "consultar_por_job", lambda job_id: {"estado": "pendiente"} if cfv in job_id else {"estado": "en_curso"})
    p = produccion.progreso("acme", escenario["sid"])
    s = p["sprint"]
    assert s["planeadas"] == 3 and s["encoladas"] == 1 and s["generando"] == 1 and s["listas"] == 0 and s["error"] == 0
    assert s["segundos_restantes"] == 180 + 60 and p["campanas"][0]["id"] == escenario["cid"]
    creative_flow.actualizar("acme", cfv, estado="video_listo", video_url="https://r2/v.mp4", usd=0.8)
    creative_flow.actualizar("acme", cfi, estado="error", error="x")
    datos.actualizar_idea("acme", escenario["iv"], revision="aprobada")
    s = produccion.progreso("acme", escenario["sid"])["sprint"]
    assert s["listas"] == 1 and s["error"] == 1 and s["aprobadas"] == 1 and abs(s["costo_usd"] - 0.8) < 1e-6 and s["segundos_restantes"] == 0
