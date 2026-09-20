"""Rutas del Blueprint nicho: validan y delegan a nicho.datos / tareas.nicho;
encolar se monkeypatchea. Sesión admin como en test_rutas_sprints."""
import io

import pytest

SUB = {"base": "emocion", "nombre": "Ana / La que carga", "deseo": "Quiero lavar sin cargar", "demografia": "", "edad_rango": "",
       "emocion": "Cansancio", "identidad": {"quiere_que_vean": "a", "cree_de_si": "b", "quiere_lograr": "c"},
       "soluciones_previas": [{"que": "Líquido", "por_que_fallo": ["pesa"]}], "situaciones": ["Cargando garrafas"],
       "comportamiento": "Sigue igual", "conciencia": {"nivel": "consciente_del_problema", "detalle": "d"},
       "encaje_producto": "Cápsulas", "tono": "Directo", "palabras_clave": ["garrafa"],
       "evidencia": [{"comentario_id": 1, "cita": "la garrafa pesa demasiado"}], "sin_evidencia": False}


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
    from nicho import rutas
    from tareas import nicho as tareas_nicho
    encolados = []
    monkeypatch.setattr(tareas_nicho.trabajos, "encolar", lambda job_id, tipo, payload, **kw: encolados.append({"job_id": job_id, "tipo": tipo, "payload": payload, **kw}) or True)
    monkeypatch.setattr(rutas.trabajos, "en_curso", lambda job_id: False)
    monkeypatch.setattr(catalogo_productos, "listar", lambda c, cat="producto": [
        {"id": "capsulas", "nombre": "Cápsulas", "descripcion": "sin plástico", "representativa_url": None}])
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    (tmp_path / "clientes" / "acme").mkdir(parents=True)
    return {"dashboard": dashboard, "c": _cliente_admin(dashboard), "encolados": encolados}


def _estudio(datos, n=25):
    eid = datos.crear_estudio("acme", "Detergente", producto="Cápsulas", tema="lavar")
    datos.agregar_comentarios("acme", eid, "texto", [{"fuente_id": f"c{i}", "texto": f"Comentario {i}: la garrafa pesa demasiado."} for i in range(n)])
    return eid


def _con_avatares(datos):
    eid = _estudio(datos)
    datos.guardar_generacion("acme", eid, [{"nombre": "Sin peso", "deseo": "Quiero lavar sin cargar", "resumen": "r", "sub_avatares": [SUB]}])
    return eid, datos.avatares("acme", eid)[0]["subs"][0]["id"]


def test_crear_estudio_y_pestana(app):
    from nicho import datos
    c = app["c"]
    r = c.post("/cliente/acme/nicho/estudios", data={"nombre": "Detergente", "producto": "Cápsulas", "tema": "lavar", "idioma": "sv", "catalogo_id": "capsulas"})
    e = datos.estudios("acme")[0]
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/cliente/acme/nicho/{e['id']}")
    assert e["idioma"] == "sv" and e["catalogo_id"] == "capsulas"
    r = c.post("/cliente/acme/nicho/estudios", data={"nombre": ""})
    assert r.status_code == 302 and r.headers["Location"].endswith("#nicho") and len(datos.estudios("acme")) == 1
    html = c.get("/cliente/acme").data.decode()
    assert 'data-tab="nicho"' in html and "Detergente" in html and "Nuevo estudio" in html


def test_contexto(app):
    from nicho import datos, rutas
    _estudio(datos)
    ctx = rutas.contexto("acme")
    assert ctx["estudios_nicho"][0]["comentarios_total"] == 25 and ctx["productos_nicho"][0]["id"] == "capsulas"
    assert ctx["min_comentarios_nicho"] == 20 and "es" in ctx["idiomas_nicho"]


def test_editar_y_archivar(app):
    from nicho import datos
    eid = _estudio(datos)
    app["c"].post(f"/cliente/acme/nicho/{eid}/editar", data={"nombre": "Otro", "idioma": "en", "catalogo_id": ""})
    e = datos.estudio("acme", eid)
    assert e["nombre"] == "Otro" and e["idioma"] == "en" and e["catalogo_id"] is None
    app["c"].post(f"/cliente/acme/nicho/{eid}/archivar")
    assert datos.estudio("acme", eid)["archivado"] is True
    app["c"].post(f"/cliente/acme/nicho/{eid}/archivar", data={"desarchivar": "1"})
    assert datos.estudio("acme", eid)["archivado"] is False
    assert app["c"].post("/cliente/otro/nicho/999/editar", data={"nombre": "x"}).status_code == 404


def test_comentarios_texto_archivo_excluir_borrar(app):
    from nicho import datos
    c = app["c"]
    eid = datos.crear_estudio("acme", "X")
    c.post(f"/cliente/acme/nicho/{eid}/comentarios/texto", data={"texto": "Pesa mucho la garrafa\nok\n\nGotea en el estante", "modo": "lineas"})
    assert datos.estudio("acme", eid)["comentarios_total"] == 2
    c.post(f"/cliente/acme/nicho/{eid}/comentarios/archivo", data={"archivo": (io.BytesIO(b"review;rating\nSe pega la tapa;4\nPesa mucho la garrafa;5\n"), "r.csv")},
           content_type="multipart/form-data")
    e = datos.estudio("acme", eid)
    assert e["fuentes"] == {"texto": {"total": 2, "excluidos": 0}, "csv": {"total": 2, "excluidos": 0}}   # el repetido no duplica dentro de su fuente
    r = c.post(f"/cliente/acme/nicho/{eid}/comentarios/archivo", data={"archivo": (io.BytesIO(b"hola"), "r.txt")}, content_type="multipart/form-data")
    assert r.status_code == 302 and datos.estudio("acme", eid)["comentarios_total"] == 4
    cid = datos.comentarios("acme", eid)["items"][0]["id"]
    c.post(f"/cliente/acme/nicho/comentario/{cid}/excluir")
    assert datos.comentario("acme", cid)["excluido"] is True and datos.estudio("acme", eid)["comentarios_activos"] == 3
    c.post(f"/cliente/acme/nicho/comentario/{cid}/excluir", data={"incluir": "1"})
    assert datos.comentario("acme", cid)["excluido"] is False
    c.post(f"/cliente/acme/nicho/{eid}/comentarios/borrar/csv")
    assert datos.estudio("acme", eid)["fuentes"] == {"texto": {"total": 2, "excluidos": 0}}
    assert c.post(f"/cliente/acme/nicho/{eid}/comentarios/borrar/magia").status_code == 404
    assert len(datos.estudio("acme", eid)["extra"]["recolecciones"]) == 2


def test_generar_encola_con_puerta(app):
    from nicho import datos
    eid = _estudio(datos, n=5)
    app["c"].post(f"/cliente/acme/nicho/{eid}/generar")
    assert app["encolados"] == []                                          # menos de 20 comentarios: no encola
    eid = _estudio(datos)
    r = app["c"].post(f"/cliente/acme/nicho/{eid}/generar")
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/nicho/{eid}")
    t = app["encolados"][0]
    assert t["tipo"] == "nicho_generar_avatares" and t["payload"] == {"cliente": "acme", "estudio_id": eid} and t["max_intentos"] == 1
    assert datos.estudio("acme", eid)["estado"] == "generando"
    datos.archivar_estudio("acme", eid)
    app["c"].post(f"/cliente/acme/nicho/{eid}/generar")
    assert len(app["encolados"]) == 1                                      # archivado: no encola


def test_avatar_editar_aprobar_descartar(app):
    from nicho import datos
    from sprints import datos as sd
    c = app["c"]
    eid, sid = _con_avatares(datos)
    c.post(f"/cliente/acme/nicho/avatar/{sid}/editar", data={
        "nombre": "Ana", "deseo": "Quiero lavar sin cargar", "base": "experiencia_producto", "demografia": "Mujer 30-45", "edad_rango": "30-45",
        "emocion": "Cansancio", "identidad_quiere_que_vean": "x", "identidad_cree_de_si": "y", "identidad_quiere_lograr": "z",
        "soluciones_previas": "Líquido :: pesa; gotea\nPods :: caros", "situaciones": "Cargando\nEn el súper", "comportamiento": "c",
        "conciencia_nivel": "muy_consciente", "conciencia_detalle": "d", "encaje_producto": "e", "tono": "t", "palabras_clave": "a, b"})
    a = datos.avatar("acme", sid)
    assert a["nombre"] == "Ana" and a["base"] == "experiencia_producto" and a["identidad"]["cree_de_si"] == "y"
    assert a["soluciones_previas"] == [{"que": "Líquido", "por_que_fallo": ["pesa", "gotea"]}, {"que": "Pods", "por_que_fallo": ["caros"]}]
    assert a["situaciones"] == ["Cargando", "En el súper"] and a["conciencia"]["nivel"] == "muy_consciente" and a["palabras_clave"] == ["a", "b"]
    assert a["evidencia"] == SUB["evidencia"]                              # la evidencia no se toca
    r = c.post(f"/cliente/acme/nicho/avatar/{sid}/aprobar")
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/nicho/{eid}")
    a = datos.avatar("acme", sid)
    assert a["estado"] == "aprobado" and sd.persona("acme", a["persona_id"])["nombre"] == "Ana"
    c.post(f"/cliente/acme/nicho/avatar/{sid}/descartar")
    assert datos.avatar("acme", sid)["estado"] == "descartado" and sd.persona("acme", a["persona_id"])["archivada"] is True
    nucleo_id = datos.avatares("acme", eid)[0]["id"]
    c.post(f"/cliente/acme/nicho/avatar/{nucleo_id}/aprobar")              # flash de error, no revienta
    assert datos.avatar("acme", nucleo_id)["estado"] == "propuesto"
    c.post(f"/cliente/acme/nicho/avatar/{nucleo_id}/descartar")            # ídem: el núcleo tampoco se descarta
    assert datos.avatar("acme", nucleo_id)["estado"] == "propuesto"
    assert c.post("/cliente/otro/nicho/avatar/999/aprobar").status_code == 404


def test_pagina_del_estudio(app):
    from nicho import datos
    eid, sid = _con_avatares(datos)
    html = app["c"].get(f"/cliente/acme/nicho/{eid}").data.decode()
    for frag in ("Detergente", "Regenerar avatares", "US$", "25 comentario(s)", "Núcleo 1: Sin peso", "Ana / La que carga",
                 "«la garrafa pesa demasiado»", "Aprobar → persona", "Exportar Excel", "Pegar texto", "Subir CSV o Excel", "Excluir",
                 "Beliefs about self"):
        assert frag in html, frag
    assert app["c"].get("/cliente/acme/nicho/999").status_code == 404
    assert app["c"].get(f"/cliente/acme/nicho/{eid}?fuente=texto&pagina=abc").status_code == 200


def test_pagina_sin_comentarios_apaga_el_boton(app):
    from nicho import datos
    eid = _estudio(datos, n=3)
    html = app["c"].get(f"/cliente/acme/nicho/{eid}").data.decode()
    assert "Hacen falta al menos 20" in html and "disabled" in html and "Todavía no hay avatares" in html


def test_pagina_con_trabajo_en_curso_muestra_progreso(app, monkeypatch):
    from nicho import datos, rutas
    eid = _estudio(datos)
    monkeypatch.setattr(rutas.trabajos, "en_curso", lambda job_id: job_id == datos.job_id_generar("acme", eid))
    html = app["c"].get(f"/cliente/acme/nicho/{eid}").data.decode()
    assert "iniciarPolling" in html and datos.job_id_generar("acme", eid) in html


def test_exportar(app):
    from nicho import datos
    eid, sid = _con_avatares(datos)
    r = app["c"].get(f"/cliente/acme/nicho/{eid}/exportar.md")
    assert r.status_code == 200 and "text/markdown" in r.content_type and "## Núcleo 1: Sin peso" in r.data.decode()
    assert "attachment" in r.headers["Content-Disposition"] and ".md" in r.headers["Content-Disposition"]
    r = app["c"].get(f"/cliente/acme/nicho/{eid}/exportar.xlsx")
    assert r.status_code == 200 and "spreadsheetml" in r.content_type and r.data[:2] == b"PK"
    assert app["c"].get(f"/cliente/otro/nicho/{eid}/exportar.md").status_code == 404
    assert app["c"].get(f"/cliente/otro/nicho/{eid}/exportar.xlsx").status_code == 404
