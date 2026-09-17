"""Rutas del Blueprint sprints: validan y delegan a sprints.datos / tareas;
encolar, R2 y ffmpeg se monkeypatchean. Sesión admin como en
test_rutas_experimentos."""
import io
import json

import pytest


def _cliente_admin(dashboard):
    dashboard.app.config["TESTING"] = True
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "admin"; s["rol"] = "admin"; s["cliente"] = None
    return c


@pytest.fixture()
def app(base_temporal, monkeypatch, tmp_path):
    import dashboard
    import catalogo_productos
    import proyectos
    from sprints import rutas
    encolados = []
    monkeypatch.setattr(rutas.trabajos, "encolar", lambda job_id, tipo, payload, **kw: encolados.append({"job_id": job_id, "tipo": tipo, "payload": payload, **kw}) or True)
    monkeypatch.setattr(rutas.trabajos, "en_curso", lambda job_id: False)
    monkeypatch.setattr(catalogo_productos, "listar", lambda c, cat="producto": [
        {"id": "espejo_led", "nombre": "Espejo LED", "descripcion": "redondo", "representativa_url": "https://r2/e.jpg"},
        {"id": "division_bano", "nombre": "División de baño", "descripcion": "", "representativa_url": None}])
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    (tmp_path / "clientes" / "acme").mkdir(parents=True)
    return {"dashboard": dashboard, "c": _cliente_admin(dashboard), "encolados": encolados}


def test_persona_crear_editar_archivar(app):
    from sprints import datos
    c = app["c"]
    r = c.post("/cliente/acme/sprints/personas", data={"nombre": "Cliente Premium", "resumen": "Busca calidad",
                                                        "senales_visuales": "cocina moderna, luz natural", "color": "#4d8dff"})
    assert r.status_code == 302 and r.headers["Location"].endswith("#sprints")
    p = datos.personas("acme")[0]
    assert p["senales_visuales"] == ["cocina moderna", "luz natural"] and p["color"] == "#4d8dff"
    c.post(f"/cliente/acme/sprints/personas/{p['id']}", data={"nombre": "Premium", "tono": "cercano"})
    assert datos.persona("acme", p["id"])["tono"] == "cercano"
    c.post(f"/cliente/acme/sprints/personas/{p['id']}/archivar")
    assert datos.personas("acme") == []
    c.post("/cliente/acme/sprints/personas", data={"nombre": ""})      # inválida: no crea
    assert datos.personas("acme") == []


def test_personas_sugerir_encola(app):
    app["c"].post("/cliente/acme/sprints/personas/sugerir", data={"cuantas": "3"})
    assert app["encolados"][0]["tipo"] == "sprint_sugerir_personas" and app["encolados"][0]["payload"]["cuantas"] == 3


def test_personas_sugerir_cuantas_no_numerica_no_revienta(app):
    r = app["c"].post("/cliente/acme/sprints/personas/sugerir", data={"cuantas": "abc"})
    assert r.status_code == 302 and r.headers["Location"].endswith("#sprints")
    assert app["encolados"] == []


def test_temporadas_crear_adoptar_pais(app):
    from sprints import datos
    import proyectos
    c = app["c"]
    c.post("/cliente/acme/sprints/temporadas", data={"nombre": "Lanzamiento", "inicio": "2026-10-01", "fin": "2026-10-20",
                                                      "tipo": "propia", "contexto": "nueva línea", "paleta": "#000, #fff"})
    t = datos.temporadas("acme")[0]
    assert t["nombre"] == "Lanzamiento" and t["mood_visual"]["paleta"] == ["#000", "#fff"]
    c.post("/cliente/acme/sprints/temporadas", data={"nombre": "Mal", "inicio": "2026-10-20", "fin": "2026-10-01"})
    assert len(datos.temporadas("acme")) == 1
    c.post("/cliente/acme/sprints/temporadas/pais", data={"pais": "MX"})
    assert proyectos.pais("acme") == "MX"
    c.post("/cliente/acme/sprints/temporadas/adoptar", data={"clave": "buen_fin", "anio": "2026"})
    assert [x["nombre"] for x in datos.temporadas("acme")] == ["Lanzamiento", "El Buen Fin"]
    c.post(f"/cliente/acme/sprints/temporadas/{t['id']}/archivar")
    assert [x["nombre"] for x in datos.temporadas("acme")] == ["El Buen Fin"]


def test_contexto_trae_lo_que_usa_la_pestana(app):
    from sprints import datos, rutas
    datos.crear_persona("acme", "Premium")
    ctx = rutas.contexto("acme")
    assert ctx["personas_sprint"][0]["nombre"] == "Premium" and ctx["sprints_lista"] == []
    assert [p["id"] for p in ctx["productos_sprint"]] == ["espejo_led", "division_bano"]
    assert ctx["pais_calendario"] == "CO" and any(p["clave"] == "navidad" for p in ctx["presets_temporadas"])
    assert ctx["estimado_sprint"]["video"] > 0 and ctx["estimado_sprint"]["imagen"] > 0
    assert "es_CO" in [d["codigo"] for d in ctx["destinos_sprint"]] and ctx["trabajo_sugerir"] is None


def test_contexto_avisa_cuando_el_pais_no_tiene_calendario_propio(app):
    from sprints import rutas
    import proyectos
    assert rutas.contexto("acme")["calendario_fallback"] is False          # CO por defecto
    proyectos.guardar_pais("acme", "US")
    ctx = rutas.contexto("acme")
    assert ctx["calendario_fallback"] is True and ctx["pais_calendario"] == "US"
    assert [p["clave"] for p in ctx["presets_temporadas"]] == [p["clave"] for p in rutas.calendario.presets("CO")]
    html = app["c"].get("/cliente/acme").data.decode()
    assert "no tiene calendario propio" in html
    proyectos.guardar_pais("acme", "CO")
    assert "no tiene calendario propio" not in app["c"].get("/cliente/acme").data.decode()


def test_contexto_fuera_de_una_peticion_no_revienta(app):
    from sprints import rutas
    assert rutas.contexto("acme")["sprint_recien_creado"] is False


def test_cliente_sin_permiso_no_entra(app):
    c = app["dashboard"].app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "otro"; s["rol"] = "cliente"; s["cliente"] = "otro"
    r = c.post("/cliente/acme/sprints/personas", data={"nombre": "X"})
    assert r.status_code == 302 and "/cliente/otro" in r.headers["Location"]
    from sprints import datos
    assert datos.personas("acme") == []


def _base(datos):
    pid = datos.crear_persona("acme", "Premium")
    tid = datos.crear_temporada("acme", "Verano", "2026-06-01", "2026-07-15")
    return pid, tid


def test_crear_sprint_con_matriz(app):
    from sprints import datos
    pid, tid = _base(datos)
    tid2 = datos.crear_temporada("acme", "Navidad", "2026-11-15", "2026-12-31")
    campanas = [{"persona_id": pid, "catalogo_id": "espejo_led", "temporada_id": tid, "n_videos": 10, "n_imagenes": 25},
                {"persona_id": pid, "catalogo_id": "espejo_led", "temporada_id": tid2, "n_videos": 3, "n_imagenes": 0}]
    r = app["c"].post("/cliente/acme/sprints/nuevo", data={"nombre": "Octubre", "inicio": "2026-10-01", "fin": "2026-10-31",
                                                           "destinos": ["es_CO", "es_MX"], "referencias_objetivo": "4",
                                                           "campanas_json": json.dumps(campanas)})
    assert r.status_code == 302 and "/sprints/" in r.headers["Location"]
    sp = datos.sprints("acme")[0]
    assert sp["destinos"] == ["es_CO", "es_MX"] and sp["campanas_total"] == 2 and sp["piezas_planeadas"] == 38
    assert sp["campanas"][0]["referencias_objetivo"] == 4 and sp["estado"] == "planeando"


def test_crear_sprint_limpia_el_borrador_del_asistente_una_sola_vez(app):
    from sprints import datos
    pid, tid = _base(datos)
    campanas = [{"persona_id": pid, "catalogo_id": "espejo_led", "temporada_id": tid, "n_videos": 1, "n_imagenes": 0}]
    c = app["c"]
    assert "sessionStorage.removeItem(KEY)" not in c.get("/cliente/acme").data.decode()
    r = c.post("/cliente/acme/sprints/nuevo", data={"nombre": "Octubre", "inicio": "2026-10-01", "fin": "2026-10-31",
                                                    "campanas_json": json.dumps(campanas)})
    assert r.status_code == 302 and datos.sprints("acme")
    html = c.get("/cliente/acme").data.decode()
    assert "sessionStorage.removeItem(KEY)" in html and "sprint-asistente-" in html
    assert "sessionStorage.removeItem(KEY)" not in c.get("/cliente/acme").data.decode()   # solo la primera vez


def test_crear_sprint_fallido_no_limpia_el_borrador(app):
    from sprints import datos
    pid, tid = _base(datos)
    c = app["c"]
    c.post("/cliente/acme/sprints/nuevo", data={"nombre": "X", "inicio": "2026-10-01", "fin": "2026-10-31", "campanas_json": "[]"})
    assert datos.sprints("acme") == []
    assert "sessionStorage.removeItem(KEY)" not in c.get("/cliente/acme").data.decode()


def test_crear_sprint_con_campanas_malformadas_no_crea_nada(app):
    from sprints import datos, rutas
    pid, tid = _base(datos)
    c = app["c"]
    for crudo in ('["x"]', '[5]', '[null]', '[[1,2]]'):
        c.post("/cliente/acme/sprints/nuevo", data={"nombre": "X", "inicio": "2026-10-01", "fin": "2026-10-31", "campanas_json": crudo})
    assert datos.sprints("acme") == [] and datos.sprints("acme", incluir_archivados=True) == []
    with pytest.raises(datos.ErrorDatos) as exc:
        rutas._validar_campanas("acme", ["x"])
    assert str(exc.value) == "Campaña 1: formato inválido."


def test_crear_sprint_rechaza_duplicados_y_productos_ajenos(app):
    from sprints import datos
    pid, tid = _base(datos)
    dup = [{"persona_id": pid, "catalogo_id": "espejo_led", "temporada_id": tid, "n_videos": 1, "n_imagenes": 0}] * 2
    app["c"].post("/cliente/acme/sprints/nuevo", data={"nombre": "X", "inicio": "2026-10-01", "fin": "2026-10-31", "campanas_json": json.dumps(dup)})
    assert datos.sprints("acme") == []
    ajeno = [{"persona_id": pid, "catalogo_id": "no_existe", "temporada_id": tid, "n_videos": 1, "n_imagenes": 0}]
    app["c"].post("/cliente/acme/sprints/nuevo", data={"nombre": "X", "inicio": "2026-10-01", "fin": "2026-10-31", "campanas_json": json.dumps(ajeno)})
    assert datos.sprints("acme") == []
    app["c"].post("/cliente/acme/sprints/nuevo", data={"nombre": "X", "inicio": "2026-10-01", "fin": "2026-10-31", "campanas_json": "[]"})
    assert datos.sprints("acme") == []
    cero = [{"persona_id": pid, "catalogo_id": "espejo_led", "temporada_id": tid, "n_videos": 0, "n_imagenes": 0}]
    app["c"].post("/cliente/acme/sprints/nuevo", data={"nombre": "X", "inicio": "2026-10-01", "fin": "2026-10-31", "campanas_json": json.dumps(cero)})
    assert datos.sprints("acme") == []


def _sprint(datos, pid, tid):
    sid = datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31")
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 2, 1)
    return sid, cid


def test_detalle_progreso_listo_y_campanas(app):
    from sprints import datos
    pid, tid = _base(datos)
    sid, cid = _sprint(datos, pid, tid)
    c = app["c"]
    r = c.get(f"/cliente/acme/sprints/{sid}")
    assert r.status_code == 200 and b"Espejo LED" in r.data and b"Premium" in r.data and b"Verano" in r.data
    assert c.get("/cliente/acme/sprints/999").status_code == 404
    j = c.get(f"/cliente/acme/sprints/{sid}/progreso").get_json()
    assert j["estado"] == "planeando" and j["campanas"][0]["etapa"] == "referencias" and j["sprint"]["planeadas"] == 3
    c.post(f"/cliente/acme/sprints/{sid}/listo")
    assert datos.sprint("acme", sid)["estado"] == "listo_para_generar"
    assert datos.sprint("acme", sid)["eventos"][0]["tipo"] == "marcado_listo"
    tid2 = datos.crear_temporada("acme", "Navidad", "2026-11-15", "2026-12-31")
    c.post(f"/cliente/acme/sprints/{sid}/campanas", data={"persona_id": pid, "catalogo_id": "division_bano", "temporada_id": tid2,
                                                         "n_videos": "1", "n_imagenes": "1"})
    assert len(datos.campanas("acme", sid)) == 2
    c.post(f"/cliente/acme/sprints/{sid}/campanas", data={"persona_id": pid, "catalogo_id": "espejo_led", "temporada_id": tid,
                                                         "n_videos": "1", "n_imagenes": "1"})       # duplicada
    assert len(datos.campanas("acme", sid)) == 2
    c.post(f"/cliente/acme/sprints/{sid}/campanas/{cid}", data={"n_videos": "7"})
    assert datos.campana("acme", cid)["n_videos"] == 7
    otro_sid = datos.crear_sprint("acme", "Otro", "2026-11-01", "2026-11-30")
    assert c.post(f"/cliente/acme/sprints/{otro_sid}/campanas/{cid}", data={"n_videos": "1"}).status_code == 404
    c.post(f"/cliente/acme/sprints/{sid}/campanas/{cid}/eliminar")
    assert len(datos.campanas("acme", sid)) == 1
    c.post(f"/cliente/acme/sprints/{sid}/archivar")
    assert datos.sprints("acme") == [datos.sprints("acme")[0]] and datos.sprints("acme")[0]["id"] == otro_sid


def test_crear_sprint_persona_inexistente_no_deja_sprint_a_medias(app):
    from sprints import datos
    pid, tid = _base(datos)
    lista = [{"persona_id": 999, "catalogo_id": "espejo_led", "temporada_id": tid, "n_videos": 1, "n_imagenes": 0}]
    app["c"].post("/cliente/acme/sprints/nuevo", data={"nombre": "X", "inicio": "2026-10-01", "fin": "2026-10-31",
                                                        "campanas_json": json.dumps(lista)})
    assert datos.sprints("acme") == []
    assert datos.sprints("acme", incluir_archivados=True) == []


def test_validar_campanas_prefija_numero_de_campana_en_error_de_cantidades(app):
    from sprints import datos, rutas
    pid, tid = _base(datos)
    with pytest.raises(datos.ErrorDatos) as exc:
        rutas._validar_campanas("acme", [{"persona_id": pid, "catalogo_id": "espejo_led", "temporada_id": tid,
                                          "n_videos": 0, "n_imagenes": 0}])
    assert str(exc.value).startswith("Campaña 1:")


def test_referencias_subir_editar_quitar(app, monkeypatch):
    from sprints import archivos, datos
    pid, tid = _base(datos)
    sid, cid = _sprint(datos, pid, tid)
    monkeypatch.setattr(archivos, "guardar_subida", lambda c, a: None if a.filename.endswith(".pdf") else {
        "tipo": "imagen", "url": f"https://r2/{a.filename}", "frame_url": None, "ruta_local": "/tmp/x", "titulo": a.filename})
    c = app["c"]
    r = c.post(f"/cliente/acme/sprints/{sid}/campanas/{cid}/referencias", data={
        "archivos": [(io.BytesIO(b"a"), "a.jpg"), (io.BytesIO(b"b"), "b.pdf")], "intencion": ["paleta"]},
        content_type="multipart/form-data")
    assert r.status_code == 302
    refs = datos.referencias("acme", cid)
    assert len(refs) == 1 and refs[0]["intencion"] == ["paleta"] and refs[0]["estado"] == "borrador"
    assert [e["tipo"] for e in app["encolados"]] == ["sprint_analizar_referencia"]
    rid = refs[0]["id"]
    r = c.post(f"/cliente/acme/sprints/referencias/{rid}", json={"descripcion": "quiero esa luz", "intencion": ["iluminacion", "otro"], "intencion_otro": "reflejos"})
    j = r.get_json()
    assert j["ok"] and j["estado"] == "lista" and j["referencias_listas"] == 1 and j["estado_sprint"] == "referencias"
    r = c.post(f"/cliente/acme/sprints/referencias/{rid}", json={"intencion": ["magia"]})
    assert r.status_code == 400 and not r.get_json()["ok"]
    page = c.get(f"/cliente/acme/sprints/{sid}/campanas/{cid}")
    assert page.status_code == 200 and b"quiero esa luz" in page.data and b"a.jpg" in page.data
    j = c.get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/referencias/estado").get_json()
    assert j["listas"] == 1 and j["referencias"][0]["analisis_estado"] == "pendiente"
    c.post(f"/cliente/acme/sprints/referencias/{rid}/reanalizar")
    assert len(app["encolados"]) == 2
    c.post(f"/cliente/acme/sprints/referencias/{rid}/quitar")
    assert datos.referencias("acme", cid) == []
    assert c.get(f"/cliente/acme/sprints/{sid}/campanas/999").status_code == 404


def test_referencias_link_catalogo_y_reutilizar(app, monkeypatch):
    from sprints import datos
    import catalogo_productos
    pid, tid = _base(datos)
    sid, cid = _sprint(datos, pid, tid)
    c = app["c"]
    c.post(f"/cliente/acme/sprints/{sid}/campanas/{cid}/referencias", data={"link": "https://www.tiktok.com/@x/video/1"})
    assert app["encolados"][-1]["tipo"] == "sprint_referencia_link" and app["encolados"][-1]["payload"]["campana_id"] == cid
    monkeypatch.setenv("R2_PUBLIC_BASE_URL", "https://r2")
    monkeypatch.setattr(catalogo_productos, "encontrar", lambda cl, pid_, categoria=None: {"id": "espejo_led", "nombre": "Espejo LED", "imagenes": ["1.jpg", "2.jpg"]})
    c.post(f"/cliente/acme/sprints/{sid}/campanas/{cid}/referencias/catalogo")
    refs = datos.referencias("acme", cid)
    assert [r["origen"] for r in refs] == ["catalogo", "catalogo"] and refs[0]["estado"] == "lista"
    assert refs[0]["url"] == "https://r2/clientes/acme/productos/espejo_led/1.jpg"
    c.post(f"/cliente/acme/sprints/{sid}/campanas/{cid}/referencias/catalogo")     # idempotente
    assert len(datos.referencias("acme", cid)) == 2
    tid2 = datos.crear_temporada("acme", "Navidad", "2026-11-15", "2026-12-31")
    cid2 = datos.agregar_campana("acme", sid, pid, "espejo_led", tid2, 1, 0)
    c.post(f"/cliente/acme/sprints/{sid}/campanas/{cid2}/referencias/reutilizar", data={"referencia_id": refs[0]["id"]})
    assert datos.referencias("acme", cid2)[0]["origen"] == "reutilizada"


def test_referencias_subir_una_falla_al_guardar_no_pierde_las_demas(app, monkeypatch):
    from sprints import archivos, datos
    pid, tid = _base(datos)
    sid, cid = _sprint(datos, pid, tid)

    def _guardar(cliente, a):
        if a.filename == "malo.mp4":
            raise RuntimeError("ffmpeg")
        return {"tipo": "imagen", "url": f"https://r2/{a.filename}", "frame_url": None, "ruta_local": "/tmp/x",
                "titulo": a.filename}

    monkeypatch.setattr(archivos, "guardar_subida", _guardar)
    c = app["c"]
    r = c.post(f"/cliente/acme/sprints/{sid}/campanas/{cid}/referencias", data={
        "archivos": [(io.BytesIO(b"a"), "malo.mp4"), (io.BytesIO(b"b"), "bueno.jpg")]},
        content_type="multipart/form-data")
    assert r.status_code == 302
    refs = datos.referencias("acme", cid)
    assert len(refs) == 1 and refs[0]["titulo"] == "bueno.jpg"
    assert [e["tipo"] for e in app["encolados"]] == ["sprint_analizar_referencia"]


def test_referencia_editar_json_no_objeto_devuelve_400(app):
    from sprints import datos
    pid, tid = _base(datos)
    sid, cid = _sprint(datos, pid, tid)
    rid = datos.agregar_referencia("acme", cid, "imagen", "https://r2/a.jpg")
    r = app["c"].post(f"/cliente/acme/sprints/referencias/{rid}", json=["descripcion"])
    assert r.status_code == 400 and r.get_json()["ok"] is False


def test_referencia_editar_campos_con_tipo_equivocado_devuelve_400(app):
    from sprints import datos
    pid, tid = _base(datos)
    sid, cid = _sprint(datos, pid, tid)
    rid = datos.agregar_referencia("acme", cid, "imagen", "https://r2/a.jpg", titulo="a.jpg")
    c = app["c"]
    for cuerpo in ({"descripcion": 5}, {"intencion_otro": ["x"]}, {"titulo": {"a": 1}}, {"intencion": "paleta"}):
        r = c.post(f"/cliente/acme/sprints/referencias/{rid}", json=cuerpo)
        assert r.status_code == 400 and r.get_json() == {"ok": False, "error": "Formato inválido."}, cuerpo
    ref = datos.referencia("acme", rid)
    assert ref["titulo"] == "a.jpg" and ref["descripcion"] == "" and ref["intencion"] == [] and ref["estado"] == "borrador"
    # None sí se acepta (se guarda vacío), y el caso bueno sigue funcionando.
    r = c.post(f"/cliente/acme/sprints/referencias/{rid}", json={"descripcion": None, "intencion_otro": None})
    assert r.status_code == 200 and r.get_json()["ok"]
    r = c.post(f"/cliente/acme/sprints/referencias/{rid}", json={"descripcion": "luz", "intencion": ["iluminacion"]})
    assert r.get_json()["estado"] == "lista"


def test_archivar_y_desarchivar_sprint_avisan_lo_que_hicieron(app):
    from sprints import datos
    pid, tid = _base(datos)
    sid, cid = _sprint(datos, pid, tid)
    c = app["c"]
    r = c.post(f"/cliente/acme/sprints/{sid}/archivar", follow_redirects=True)
    assert "Sprint archivado." in r.data.decode() and datos.sprints("acme") == []
    r = c.post(f"/cliente/acme/sprints/{sid}/archivar", data={"desarchivar": "1"}, follow_redirects=True)
    assert "Sprint desarchivado." in r.data.decode() and "Sprint archivado." not in r.data.decode()
    assert [s["id"] for s in datos.sprints("acme")] == [sid]


def _cliente_ajeno(dashboard, cliente="otro"):
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = cliente; s["rol"] = "cliente"; s["cliente"] = cliente
    return c


def test_referencias_de_otro_proyecto_no_se_tocan_desde_una_sesion_de_cliente(app):
    """Las rutas de referencia llevan solo <rid>: la sesión de un cliente
    ajeno tiene que rebotar en _guard_por_cliente sin que se edite, quite,
    reanalice ni reutilice nada."""
    from sprints import datos
    pid, tid = _base(datos)
    sid, cid = _sprint(datos, pid, tid)
    rid = datos.agregar_referencia("acme", cid, "imagen", "https://r2/a.jpg", titulo="a.jpg", intencion=["paleta"])
    tid2 = datos.crear_temporada("acme", "Navidad", "2026-11-15", "2026-12-31")
    cid2 = datos.agregar_campana("acme", sid, pid, "espejo_led", tid2, 1, 0)
    antes = datos.referencia("acme", rid)
    ajeno = _cliente_ajeno(app["dashboard"])
    intentos = [
        ajeno.post(f"/cliente/acme/sprints/referencias/{rid}", json={"descripcion": "hackeada", "titulo": "x"}),
        ajeno.post(f"/cliente/acme/sprints/referencias/{rid}/quitar"),
        ajeno.post(f"/cliente/acme/sprints/referencias/{rid}/reanalizar"),
        ajeno.post(f"/cliente/acme/sprints/{sid}/campanas/{cid2}/referencias/reutilizar", data={"referencia_id": rid}),
    ]
    for r in intentos:
        assert r.status_code == 302 and "/cliente/otro" in r.headers["Location"], r.headers.get("Location")
    assert datos.referencia("acme", rid) == antes
    assert datos.referencias("acme", cid2) == [] and app["encolados"] == []


def test_referencia_editar_de_otro_cliente_da_404_aunque_sea_admin(app):
    """<rid> es global, pero la referencia se busca siempre con el <cliente>
    de la URL: un admin editando /cliente/acme/... no alcanza filas de otro."""
    from sprints import datos
    pid = datos.crear_persona("otro", "Premium")
    tid = datos.crear_temporada("otro", "Verano", "2026-06-01", "2026-07-15")
    sid = datos.crear_sprint("otro", "Octubre", "2026-10-01", "2026-10-31")
    cid = datos.agregar_campana("otro", sid, pid, "espejo_led", tid, 1, 0)
    rid = datos.agregar_referencia("otro", cid, "imagen", "https://r2/a.jpg", titulo="a.jpg")
    r = app["c"].post(f"/cliente/acme/sprints/referencias/{rid}", json={"descripcion": "cruzada"})
    assert r.status_code == 404
    assert app["c"].post(f"/cliente/acme/sprints/referencias/{rid}/quitar").status_code == 404
    assert app["c"].post(f"/cliente/acme/sprints/referencias/{rid}/reanalizar").status_code == 404
    assert datos.referencia("otro", rid)["descripcion"] == "" and app["encolados"] == []


def test_pestana_sprints_se_renderiza(app):
    from sprints import datos
    pid, tid = _base(datos)
    sid, cid = _sprint(datos, pid, tid)
    r = app["c"].get("/cliente/acme")
    assert r.status_code == 200
    html = r.data.decode()
    assert 'id="tab-sprints"' in html and 'data-tab="sprints"' in html
    assert "Octubre" in html and "Premium" in html and "Verano" in html and "Nuevo sprint" in html
    assert "campanas_json" in html and "Sugerir personas" in html and "Black Friday" in html


@pytest.fixture()
def con_ideas(app, monkeypatch):
    import catalogo_productos, marca, proyectos
    from sprints import datos
    from storage import r2_uploader
    monkeypatch.setattr(marca, "guia_efectiva", lambda c: "Luz natural.")
    monkeypatch.setattr(marca, "negative_prompt_efectivo", lambda c: None)
    monkeypatch.setattr(catalogo_productos, "encontrar", lambda c, pid, categoria=None: {
        "id": "espejo_led", "nombre": "Espejo LED", "descripcion": "redondo", "regla": "Idéntico.", "categoria": "producto",
        "referencias": ["/tmp/e/1.jpg"], "imagenes": ["1.jpg"]})
    monkeypatch.setattr(r2_uploader, "upload_image", lambda ruta, key: f"https://r2/{key}")
    monkeypatch.setattr(proyectos, "preferencias_flowplus", lambda c: {"modelo_video": "wan3", "modelo_imagen": "seedream_v5_pro"})
    pid, tid = _base(datos)
    sid, cid = _sprint(datos, pid, tid)                      # 2 videos, 1 imagen
    iv = datos.crear_idea("acme", cid, "video", "Amanecer", "rodea el espejo", sonido="pájaros", gancho="Luz", duracion_s=8, estado_idea="aprobada")
    ii = datos.crear_idea("acme", cid, "imagen", "Marco", "primer plano")
    return dict(app, sid=sid, cid=cid, iv=iv, ii=ii)


def test_pagina_de_ideas_y_acciones(con_ideas):
    from sprints import datos
    c, sid, cid, iv, ii = con_ideas["c"], con_ideas["sid"], con_ideas["cid"], con_ideas["iv"], con_ideas["ii"]
    r = c.get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/ideas")
    assert r.status_code == 200 and b"Amanecer" in r.data and b"Marco" in r.data and "1 de 2 videos".encode() in r.data
    c.post(f"/cliente/acme/sprints/{sid}/campanas/{cid}/ideas/proponer", data={})
    assert con_ideas["encolados"][-1]["tipo"] == "sprint_proponer_ideas" and con_ideas["encolados"][-1]["payload"]["n_videos"] is None
    c.post(f"/cliente/acme/sprints/{sid}/campanas/{cid}/ideas/proponer", data={"mas": "3"})
    assert con_ideas["encolados"][-1]["payload"] == {"cliente": "acme", "campana_id": cid, "n_videos": 3, "n_imagenes": 0, "reemplaza": None}
    r = c.post(f"/cliente/acme/sprints/ideas/{ii}", json={"titulo": "Marco cálido", "escena": "primer plano con luz", "gancho": "Detalle"})
    assert r.get_json()["ok"] and datos.idea("acme", ii)["titulo"] == "Marco cálido"
    c.post(f"/cliente/acme/sprints/ideas/{ii}/aprobar")
    assert datos.idea("acme", ii)["estado_idea"] == "aprobada"
    c.post(f"/cliente/acme/sprints/ideas/{ii}/otra")
    # F4: la ruta solo encola; descartar la idea vieja lo hace la tarea (ideas.proponer(reemplaza=)) al reemplazarla
    assert con_ideas["encolados"][-1]["payload"]["reemplaza"] == ii and datos.idea("acme", ii)["estado_idea"] == "aprobada"
    i3 = datos.crear_idea("acme", cid, "video", "Tercera", "x")
    c.post(f"/cliente/acme/sprints/{sid}/campanas/{cid}/ideas/aprobar_todas")
    assert datos.idea("acme", i3)["estado_idea"] == "aprobada"
    c.post(f"/cliente/acme/sprints/ideas/{i3}/descartar")
    assert datos.idea("acme", i3)["estado_idea"] == "descartada"
    assert c.get(f"/cliente/acme/sprints/{sid}/campanas/999/ideas").status_code == 404
    assert c.post("/cliente/acme/sprints/ideas/999/aprobar").status_code == 404


def test_otra_idea_no_descarta_si_ya_hay_una_propuesta_en_curso(con_ideas, monkeypatch):
    """F4: si `encolar_ideas` devuelve False (misma campaña ya proponiendo),
    la idea no se pierde: sigue aprobada/propuesta y no cambia nada."""
    from sprints import datos, rutas
    c, sid, cid, iv, ii = con_ideas["c"], con_ideas["sid"], con_ideas["cid"], con_ideas["iv"], con_ideas["ii"]
    monkeypatch.setattr(rutas.tareas_sprints, "encolar_ideas", lambda *a, **k: False)
    r = c.post(f"/cliente/acme/sprints/ideas/{iv}/otra")
    assert r.status_code == 302 and datos.idea("acme", iv)["estado_idea"] == "aprobada"
    r = c.post(f"/cliente/acme/sprints/ideas/{ii}/otra")
    assert r.status_code == 302 and datos.idea("acme", ii)["estado_idea"] == "propuesta"
    with c.session_transaction() as s:
        flashes = s.get("_flashes") or []
    assert any("propuesta en curso" in m for _, m in flashes)


def test_descartar_se_niega_con_una_pieza_en_marcha(con_ideas):
    """E3: un POST a descartar sobre una idea con sesión (el botón está
    oculto, pero la petición puede fabricarse) no la saca de los conteos;
    con una reserva vencida (sin sesión real) sí se puede descartar."""
    from sprints import datos
    c, sid, iv = con_ideas["c"], con_ideas["sid"], con_ideas["iv"]
    datos.actualizar_idea("acme", iv, cf_id="cf_real")
    r = c.post(f"/cliente/acme/sprints/ideas/{iv}/descartar")
    assert r.status_code == 302 and datos.idea("acme", iv)["estado_idea"] == "aprobada"
    r = c.post(f"/cliente/acme/sprints/ideas/{iv}/otra")
    assert r.status_code == 302 and datos.idea("acme", iv)["estado_idea"] == "aprobada"
    r = c.post(f"/cliente/acme/sprints/ideas/{iv}/descartar", headers={"X-Requested-With": "fetch"})
    assert r.status_code == 400 and not r.get_json()["ok"]
    datos.actualizar_idea("acme", iv, cf_id=datos.reserva_placeholder(iv, ahora=1))     # reserva vencida
    c.post(f"/cliente/acme/sprints/ideas/{iv}/descartar")
    assert datos.idea("acme", iv)["estado_idea"] == "descartada"


def test_reserva_vencida_vuelve_a_ofrecer_generar_lote(con_ideas):
    """F1: con una reserva colgada (vencida) la página del sprint y la de
    ideas vuelven a ofrecer «Generar lote»; con una reserva viva, no."""
    from sprints import datos
    c, sid, cid, iv = con_ideas["c"], con_ideas["sid"], con_ideas["cid"], con_ideas["iv"]
    datos.actualizar_idea("acme", iv, cf_id=datos.reserva_placeholder(iv))          # viva: otro lote la tiene
    html = c.get(f"/cliente/acme/sprints/{sid}").data.decode()
    assert "Generar lote del sprint" not in html
    assert "Generar lote de esta campaña" not in c.get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/ideas").data.decode()
    datos.actualizar_idea("acme", iv, cf_id=datos.reserva_placeholder(iv, ahora=1))  # vencida
    html = c.get(f"/cliente/acme/sprints/{sid}").data.decode()
    assert "Generar lote del sprint (1)" in html and "Generar lote (1)" in html
    html = c.get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/ideas").data.decode()
    assert "Generar lote de esta campaña (1)" in html and "Otra idea" in html


def test_estimar_y_lanzar_lote(con_ideas, monkeypatch):
    import flowplus_lanzar
    from sprints import datos
    c, sid, cid, iv = con_ideas["c"], con_ideas["sid"], con_ideas["cid"], con_ideas["iv"]
    j = c.get(f"/cliente/acme/sprints/{sid}/lote/estimar?campana_id={cid}").get_json()
    assert j["videos"] == 1 and j["imagenes"] == 0 and j["usd"] > 0 and "USD" in j["texto"] and j["modelo_video"] == "wan3"
    j2 = c.get(f"/cliente/acme/sprints/{sid}/lote/estimar?modelo_video=kling_o3_pro").get_json()
    assert j2["modelo_video"] == "kling_o3_pro" and j2["usd"] > j["usd"]
    lanzados = []
    monkeypatch.setattr(flowplus_lanzar, "lanzar", lambda cl, cf, e, prioridad=5: lanzados.append((cf, prioridad)) or True)
    r = c.post(f"/cliente/acme/sprints/{sid}/lote", data={"campana_id": cid, "modelo_video": "wan3", "modelo_imagen": "seedream_v5_pro"})
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/sprints/{sid}")
    assert len(lanzados) == 1 and lanzados[0][1] == 3
    i = datos.idea("acme", iv)
    assert i["cf_id"] == lanzados[0][0]
    j = c.get(f"/cliente/acme/sprints/{sid}/progreso").get_json()
    assert j["lote"]["planeadas"] == 3 and j["lote"]["encoladas"] + j["lote"]["generando"] == 1 and j["campanas"][0]["lote"]["planeadas"] == 3
    import creative_flow
    creative_flow.actualizar("acme", i["cf_id"], estado="error", error="x")
    c.post(f"/cliente/acme/sprints/ideas/{iv}/reintentar")
    assert lanzados[-1][0] == i["cf_id"] and len(lanzados) == 2
    creative_flow.actualizar("acme", i["cf_id"], estado="video_listo", video_url="https://r2/v.mp4")
    c.post(f"/cliente/acme/sprints/ideas/{iv}/regenerar")
    assert len(lanzados) == 3 and datos.idea("acme", iv)["cf_id"] == lanzados[-1][0]
    r = c.get("/cliente/acme")
    assert "Sprint · Campaña 1".encode() in r.data      # distintivo en la tarjeta de Crear


def _con_piezas(con_ideas, monkeypatch, tmp_path):
    import creative_flow
    import estado as estado_videos
    from sprints import datos
    monkeypatch.setattr(estado_videos, "_path", lambda c: str(tmp_path / f"{c}_videos.json"))
    sid, cid, iv, ii = con_ideas["sid"], con_ideas["cid"], con_ideas["iv"], con_ideas["ii"]
    datos.actualizar_idea("acme", ii, estado_idea="aprobada")
    cfs = {}
    for cp, tipo, est, qa in ((iv, "video", "video_listo", {"veredicto": "pasa", "score": 90, "checks": {"formato": {"ok": True, "nota": "9:16"}}}),
                              (ii, "imagen", "video_listo", {"veredicto": "revisar", "score": 55, "checks": {}})):
        cf = creative_flow.crear("acme", [], ["E"], [], "x", 8, "", "A")
        creative_flow.actualizar("acme", cf, tipo=tipo, estado=est, video_url=f"https://r2/{cp}.{'mp4' if tipo == 'video' else 'png'}", usd=0.4)
        datos.actualizar_idea("acme", cp, cf_id=cf, qa=qa)
        cfs[cp] = cf
    return sid, cid, iv, ii, cfs


def test_revision_pagina_y_acciones(con_ideas, monkeypatch, tmp_path):
    from sprints import datos
    sid, cid, iv, ii, cfs = _con_piezas(con_ideas, monkeypatch, tmp_path)
    c = con_ideas["c"]
    r = c.get(f"/cliente/acme/sprints/{sid}/revision")
    assert r.status_code == 200 and b"Amanecer" in r.data and b"Marco" in r.data and b"90" in r.data and "Aprobar todas las que pasaron QA".encode() in r.data
    # F3: los atajos A/R/flechas ignoran Cmd/Ctrl/Alt (Cmd+A o Cmd+R son del navegador) y toleran activeElement nulo
    html = r.data.decode()
    assert "if (e.metaKey || e.ctrlKey || e.altKey) return;" in html and "activo && ['INPUT', 'TEXTAREA', 'SELECT']" in html
    r = c.post(f"/cliente/acme/sprints/ideas/{iv}/revision", json={"accion": "aprobar"})
    assert r.get_json()["ok"] and r.get_json()["revision"] == "aprobada"
    r = c.post(f"/cliente/acme/sprints/ideas/{ii}/revision", json={"accion": "rechazar", "motivo": ""})
    assert r.status_code == 400 and not r.get_json()["ok"]
    r = c.post(f"/cliente/acme/sprints/ideas/{ii}/revision", json={"accion": "rechazar", "motivo": "encuadre"})
    assert r.get_json()["ok"] and datos.idea("acme", ii)["revision_motivo"] == "encuadre"
    r = c.post(f"/cliente/acme/sprints/ideas/{ii}/revision", json={"accion": "volar"})
    assert r.status_code == 400
    datos.actualizar_idea("acme", iv, revision="pendiente")
    c.post(f"/cliente/acme/sprints/{sid}/revision/aprobar_qa")
    assert datos.idea("acme", iv)["revision"] == "aprobada"


def test_repetir_qa_limpia_el_marcador_y_encola_un_solo_qa(con_ideas, monkeypatch, tmp_path):
    """F5: una pieza cuyo QA falló muestra el motivo y «Repetir QA»; el POST
    borra el marcador y encola exactamente un `sprint_qa_pieza` (nunca
    generación) y vuelve a la bandeja."""
    from sprints import datos
    sid, cid, iv, ii, cfs = _con_piezas(con_ideas, monkeypatch, tmp_path)
    c = con_ideas["c"]
    datos.actualizar_idea("acme", iv, qa={"veredicto": "error", "score": None, "checks": {}, "nota": "ffprobe no responde", "cf_id": cfs[iv]})
    html = c.get(f"/cliente/acme/sprints/{sid}/revision").data.decode()
    assert "QA falló: ffprobe no responde" in html and "Repetir QA" in html and f"/sprints/ideas/{iv}/qa" in html
    n_antes = len(con_ideas["encolados"])
    r = c.post(f"/cliente/acme/sprints/ideas/{iv}/qa")
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/sprints/{sid}/revision")
    nuevos = con_ideas["encolados"][n_antes:]
    assert len(nuevos) == 1 and nuevos[0]["tipo"] == "sprint_qa_pieza" and nuevos[0]["job_id"] == f"acme__cp{iv}__qa"
    assert nuevos[0]["payload"] == {"cliente": "acme", "cp_id": iv} and datos.idea("acme", iv)["qa"] is None
    # una pieza que no está lista no se manda a QA (gastaría centavos a ciegas)
    import creative_flow
    creative_flow.actualizar("acme", cfs[ii], estado="error", error="x")
    r = c.post(f"/cliente/acme/sprints/ideas/{ii}/qa")
    assert r.status_code == 302 and len(con_ideas["encolados"]) == n_antes + 1
    assert c.post("/cliente/acme/sprints/ideas/999/qa").status_code == 404


def test_cerrar_reabrir_y_entrega(con_ideas, monkeypatch, tmp_path):
    from sprints import datos, revision
    sid, cid, iv, ii, cfs = _con_piezas(con_ideas, monkeypatch, tmp_path)
    c = con_ideas["c"]
    # La campaña planea 3 piezas y solo 2 tienen sesión: el sprint sigue en "generando"? No: no hay piezas pendientes/generando,
    # y las dos terminaron → la campaña está en revisión (estado_campana mira las piezas existentes).
    r = c.post(f"/cliente/acme/sprints/{sid}/cerrar")
    assert r.status_code == 302 and datos.sprint("acme", sid)["estado"] in ("completado", "revision")
    if datos.sprint("acme", sid)["estado"] != "completado":
        revision.aprobar("acme", iv)
        c.post(f"/cliente/acme/sprints/{sid}/cerrar")
    assert datos.sprint("acme", sid)["estado"] == "completado"
    revision.aprobar("acme", iv)
    r = c.get(f"/cliente/acme/sprints/{sid}/entrega")
    assert r.status_code == 200 and b"https://r2/" in r.data and "Descargar aprobadas".encode() in r.data
    c.post(f"/cliente/acme/sprints/{sid}/entrega/zip")
    assert con_ideas["encolados"][-1]["tipo"] == "sprint_empaquetar" and con_ideas["encolados"][-1]["payload"]["sprint_id"] == sid
    c.post(f"/cliente/acme/sprints/{sid}/reabrir")
    assert datos.sprint("acme", sid)["estado"] == "revision"
    assert c.get("/cliente/acme/sprints/999/revision").status_code == 404
    assert c.get("/cliente/acme/sprints/999/entrega").status_code == 404


def test_cerrar_y_zip_se_niegan_fuera_de_estado_y_la_entrega_muestra_el_zip(con_ideas, monkeypatch, tmp_path):
    from sprints import datos, rutas
    sid, cid, iv, ii, cfs = _con_piezas(con_ideas, monkeypatch, tmp_path)
    c = con_ideas["c"]
    vacio = datos.crear_sprint("acme", "Vacío", "2026-11-01", "2026-11-30")      # planeando: no se cierra ni se reabre
    r = c.post(f"/cliente/acme/sprints/{vacio}/cerrar")
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/sprints/{vacio}") and datos.sprint("acme", vacio)["estado"] == "planeando"
    c.post(f"/cliente/acme/sprints/{vacio}/reabrir")
    assert datos.sprint("acme", vacio)["estado"] == "planeando"
    n_antes = len(con_ideas["encolados"])
    c.post(f"/cliente/acme/sprints/{vacio}/entrega/zip")                         # sin aprobadas: no encola nada
    assert len(con_ideas["encolados"]) == n_antes
    html = c.get(f"/cliente/acme/sprints/{vacio}/entrega").data.decode()
    assert "Sin piezas aprobadas todavía" in html and 'id="copiar-enlaces" disabled' in html
    datos.actualizar_extra_sprint("acme", sid, lambda e: {**e, "zip": {"url": "https://r2/z.zip", "n": 1, "creado_en": "2026-09-17T10:00:00"}})
    monkeypatch.setattr(rutas.trabajos, "en_curso", lambda job_id: True)
    html = c.get(f"/cliente/acme/sprints/{sid}/entrega").data.decode()
    assert "https://r2/z.zip" in html and "Zip del 2026-09-17 10:00:00 (1 piezas)" in html
    assert "iniciarPolling" in html and rutas.tareas_sprints.job_id_zip("acme", sid) in html
