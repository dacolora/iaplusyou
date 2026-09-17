"""Rutas del Blueprint sprints: validan y delegan a sprints.datos / tareas;
encolar, R2 y ffmpeg se monkeypatchean. Sesión admin como en
test_rutas_experimentos."""
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
