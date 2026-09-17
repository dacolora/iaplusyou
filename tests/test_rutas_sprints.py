"""Rutas del Blueprint sprints: validan y delegan a sprints.datos / tareas;
encolar, R2 y ffmpeg se monkeypatchean. Sesión admin como en
test_rutas_experimentos."""
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
