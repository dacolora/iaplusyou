"""Rutas del Blueprint nicho: validan y delegan a nicho.datos / tareas.nicho;
encolar se monkeypatchea. Sesión admin como en test_rutas_sprints."""
import io

import pytest

from catalogo_productos import listar_productos as _listar_productos_real

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
    monkeypatch.setattr(catalogo_productos, "listar_productos", lambda c, cat="producto": [
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
    assert e["idioma"] == "es" and e["catalogo_id"] == "capsulas"
    r = c.post("/cliente/acme/nicho/estudios", data={"nombre": ""})
    assert r.status_code == 302 and r.headers["Location"].endswith("#nicho") and len(datos.estudios("acme")) == 1
    html = c.get("/cliente/acme").data.decode()
    assert 'data-tab="nicho"' in html and "Detergente" in html and "Nuevo estudio" in html

    import idiomas
    idiomas.guardar_de_proyecto("acme", "en")        # el fixture ya apunta proyectos.BASE_DIR a tmp
    c.post("/cliente/acme/nicho/estudios", data={"nombre": "Laundry"})
    assert next(x for x in datos.estudios("acme") if x["nombre"] == "Laundry")["idioma"] == "en"
    pestana = html[html.index('<section id="tab-nicho"'):html.index('<section id="tab-referentes"')]
    assert 'name="idioma"' not in pestana             # sin selector en «Nuevo estudio»


def test_idioma_de_busqueda_de_youtube_sale_del_pais_del_proyecto(app, monkeypatch):
    """Revisión final de la fase 5 (minor 5): con inglés por defecto, el idioma
    de BÚSQUEDA de YouTube no puede seguir al idioma del estudio (spec §B5 lo
    separa del idioma de salida): sale del país del proyecto."""
    import idiomas
    import proyectos
    from nicho import datos
    monkeypatch.setenv("YOUTUBE_API_KEY", "clave-de-prueba")
    idiomas.guardar_de_proyecto("acme", "en")
    monkeypatch.setattr(proyectos, "pais", lambda c: "CO")
    eid = datos.crear_estudio("acme", "Laundry", producto="Pods", tema="laundry", idioma="en")
    html = app["c"].get(f"/cliente/acme/nicho/{eid}").data.decode()
    assert 'name="idioma" value="es"' in html          # país CO → español, aunque el estudio esté en inglés


def test_contexto(app):
    from nicho import datos, rutas
    _estudio(datos)
    ctx = rutas.contexto("acme")
    assert ctx["estudios_nicho"][0]["comentarios_total"] == 25 and ctx["productos_nicho"][0]["id"] == "capsulas"
    assert ctx["min_comentarios_nicho"] == 20 and "idiomas_nicho" not in ctx


def test_selector_de_producto_del_estudio_es_uno_por_producto(app, monkeypatch, tmp_path):
    """Revisión final (catálogo por colores): Nicho elige un PRODUCTO, no
    cada color (`listar_productos`, id = pid); un estudio guardado con un id
    de color de antes («original/pink») sigue mostrando su producto elegido
    (encontrar(pid) cae al primer color, así que el pid sigue resolviendo)."""
    import catalogo_productos
    from nicho import datos, rutas
    monkeypatch.setattr(catalogo_productos, "listar_productos", _listar_productos_real)
    monkeypatch.setattr(catalogo_productos, "BASE_DIR", str(tmp_path))
    carpeta = tmp_path / "clientes" / "acme" / "productos" / "original"
    for color in ("pink", "beige"):
        (carpeta / color).mkdir(parents=True)
        (carpeta / color / "01.jpg").write_bytes(b"\xff\xd8\xff\xe0fake")
    catalogo_productos.guardar_meta("acme", {"original": {"nombre": "Original", "descripcion": "chancla de goma", "variantes": {
        "pink": {"nombre": "Original — Pink"}, "beige": {"nombre": "Original — Beige"}}}})
    assert rutas._productos("acme") == [{"id": "original", "nombre": "Original", "descripcion": "chancla de goma"}]
    assert catalogo_productos.encontrar("acme", "original")["id"] == "original/pink"
    eid = datos.crear_estudio("acme", "Chanclas", producto="Chanclas", catalogo_id="original/pink")
    html = app["c"].get(f"/cliente/acme/nicho/{eid}").data.decode()
    assert '<option value="original" selected>Original</option>' in html
    assert "original/pink" not in html.split('name="catalogo_id"', 1)[1].split("</select>", 1)[0]


def test_editar_y_archivar(app):
    from nicho import datos
    eid = _estudio(datos)
    app["c"].post(f"/cliente/acme/nicho/{eid}/editar", data={"nombre": "Otro", "idioma": "en", "catalogo_id": ""})
    e = datos.estudio("acme", eid)
    assert e["nombre"] == "Otro" and e["idioma"] == "es" and e["catalogo_id"] is None
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
    assert sd.persona("acme", a["persona_id"])["origen"] == "investigada"      # la pestaña Sprints ya no lista personas (37ab05e)
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
    for frag in ("Detergente", "Regenerar avatares", "US$", "Texto pegado: 25", "Núcleo 1: Sin peso", "Ana / La que carga",
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


@pytest.fixture()
def llaves(monkeypatch):
    monkeypatch.setenv("REDDIT_CLIENT_ID", "id")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "s")
    monkeypatch.setenv("REDDIT_USER_AGENT", "creatv/1.0 (by u/x)")
    monkeypatch.setenv("YOUTUBE_API_KEY", "k")
    monkeypatch.setenv("APIFY_TOKEN", "t")


def test_recolectar_reddit_encola_con_params(app, llaves):
    from nicho import datos
    eid = datos.crear_estudio("acme", "X", idioma="sv")
    r = app["c"].post(f"/cliente/acme/nicho/{eid}/recolectar/reddit", data={
        "palabras_clave": "foot pain", "subreddits": "Sneakers, r/BuyItForLife", "links": "https://redd.it/abc123\n\nnada",
        "max_posts": "30", "max_comentarios_por_post": "40", "periodo": "month"})
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/nicho/{eid}")
    t = app["encolados"][0]
    assert t["tipo"] == "nicho_recolectar" and t["max_intentos"] == 2 and t["payload"]["fuente"] == "reddit"
    assert t["payload"]["params"] == {"palabras_clave": "foot pain", "subreddits": ["Sneakers", "r/BuyItForLife"], "links": ["https://redd.it/abc123", "nada"],
                                      "max_posts": 30, "max_comentarios_por_post": 40, "periodo": "month"}
    app["c"].post(f"/cliente/acme/nicho/{eid}/recolectar/reddit", data={"palabras_clave": "", "links": ""})
    assert len(app["encolados"]) == 1                                            # sin palabras ni links: no encola


def test_recolectar_youtube_toma_idioma_y_pais_del_proyecto(app, llaves):
    from nicho import datos
    eid = datos.crear_estudio("acme", "X", idioma="sv")
    app["c"].post(f"/cliente/acme/nicho/{eid}/recolectar/youtube", data={"palabras_clave": "slippers", "max_videos": "3"})
    p = app["encolados"][0]["payload"]["params"]
    assert p["idioma"] == "sv" and p["region"] == "CO" and p["max_videos"] == 3 and p["max_comentarios_por_video"] == 100 and p["links"] == []


def test_recolectar_sin_llaves_no_encola(app, monkeypatch):
    from nicho import datos
    for v in ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT", "YOUTUBE_API_KEY", "APIFY_TOKEN"):
        monkeypatch.delenv(v, raising=False)
    eid = datos.crear_estudio("acme", "X")
    app["c"].post(f"/cliente/acme/nicho/{eid}/recolectar/reddit", data={"palabras_clave": "x"})
    app["c"].post(f"/cliente/acme/nicho/{eid}/recolectar/youtube", data={"palabras_clave": "x"})
    assert app["encolados"] == []


def test_recolectar_apify_valida_links_y_estimado(app, llaves):
    from nicho import datos
    eid = datos.crear_estudio("acme", "X")
    c = app["c"]
    c.post(f"/cliente/acme/nicho/{eid}/recolectar/apify", data={"actor": "amazon_resenas", "links": "https://www.amazon.com/s?k=slippers", "max_resultados": "100"})
    assert app["encolados"] == []                                                # link que no es de producto: no encola
    c.post(f"/cliente/acme/nicho/{eid}/recolectar/apify", data={"actor": "amazon_resenas", "links": "https://www.amazon.com/dp/B0TEST1234", "max_resultados": "100"})
    t = app["encolados"][0]
    assert t["max_intentos"] == 1 and t["payload"]["params"] == {"actor": "amazon_resenas", "links": ["https://www.amazon.com/dp/B0TEST1234"], "max_resultados": 100}
    r = c.get(f"/cliente/acme/nicho/{eid}/recolectar/apify/estimar?actor=tiktok_comentarios&max=400")
    assert r.status_code == 200 and r.get_json() == {"actor": "clockworks~tiktok-comments-scraper", "max_resultados": 400, "usd": 0.2, "texto": "US$ 0,20"}
    assert c.get(f"/cliente/acme/nicho/{eid}/recolectar/apify/estimar?actor=magia&max=1").status_code == 400
    assert c.get("/cliente/acme/nicho/999/recolectar/apify/estimar?actor=tiktok_comentarios&max=1").status_code == 404


def test_recolectar_archivado_fuente_desconocida_y_doble_clic(app, llaves, monkeypatch):
    from nicho import datos
    from tareas import nicho as tareas_nicho
    eid = datos.crear_estudio("acme", "X")
    assert app["c"].post(f"/cliente/acme/nicho/{eid}/recolectar/magia", data={}).status_code == 404
    datos.archivar_estudio("acme", eid)
    app["c"].post(f"/cliente/acme/nicho/{eid}/recolectar/reddit", data={"palabras_clave": "x"})
    assert app["encolados"] == []
    datos.archivar_estudio("acme", eid, archivado=False)
    monkeypatch.setattr(tareas_nicho.trabajos, "encolar", lambda *a, **k: False)
    r = app["c"].post(f"/cliente/acme/nicho/{eid}/recolectar/reddit", data={"palabras_clave": "x"}, follow_redirects=True)
    assert "en curso" in r.data.decode()


def test_ver_trae_fuentes_conectadas_y_recolecciones(app, llaves, monkeypatch):
    from nicho import datos, rutas
    eid = _estudio(datos)
    datos.registrar_recoleccion("acme", eid, {"fuente": "reddit", "nuevos": 12, "repetidos": 3, "aviso": "Reddit limitó las llamadas"})
    monkeypatch.setattr(rutas.trabajos, "en_curso", lambda job_id: job_id.endswith(":recolectar:youtube"))
    html = app["c"].get(f"/cliente/acme/nicho/{eid}").data.decode()
    assert "Reddit" in html and "YouTube" in html and "Apify" in html
    assert datos.job_id_recolectar("acme", eid, "youtube") in html and "12 nuevo" in html and "Reddit limitó" in html


def test_pagina_tarjetas_sin_llaves(app, monkeypatch):
    from nicho import datos
    for v in ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT", "YOUTUBE_API_KEY", "APIFY_TOKEN"):
        monkeypatch.delenv(v, raising=False)
    eid = datos.crear_estudio("acme", "X")
    html = app["c"].get(f"/cliente/acme/nicho/{eid}").data.decode()
    assert "(falta REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT)" in html
    assert "(falta YOUTUBE_API_KEY)" in html and "(falta APIFY_TOKEN)" in html
    assert "Puesta a punto" in html


def test_cliente_no_ve_fuentes_sin_llave_ni_instrucciones_del_servidor(app, monkeypatch):
    """Las llaves de Reddit/YouTube/Apify son de Creatv (las pone el admin en
    el .env): al cliente no se le muestra una fuente apagada ni «configura el
    .env» (2026-09-27). Las que sí tienen llave se ven normales."""
    from nicho import datos
    for v in ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT", "YOUTUBE_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("APIFY_TOKEN", "tok-prueba")
    eid = datos.crear_estudio("acme", "X")
    c = app["dashboard"].app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "user_acme"; s["rol"] = "cliente"; s["cliente"] = "acme"
    html = c.get(f"/cliente/acme/nicho/{eid}").data.decode()
    assert "nicho-fuente-apify" in html
    assert "nicho-fuente-reddit" not in html and "nicho-fuente-youtube" not in html
    assert "(falta " not in html and ".env" not in html
    c.post(f"/cliente/acme/nicho/{eid}/recolectar/reddit", data={"palabras_clave": "x"})
    with c.session_transaction() as s:
        mensajes = [m for _, m in s.get("_flashes", [])]
    assert mensajes and not any(".env" in m or "REDDIT_" in m for m in mensajes)


def test_pagina_tarjetas_con_llaves(app, llaves):
    from nicho import datos
    eid = datos.crear_estudio("acme", "X", idioma="en")
    html = app["c"].get(f"/cliente/acme/nicho/{eid}").data.decode()
    assert 'name="subreddits"' in html and 'name="periodo"' in html and 'value="year" selected' in html
    # El idioma de búsqueda de YouTube sale del país del proyecto (CO → es), no del idioma del estudio.
    assert 'name="max_videos"' in html and 'name="idioma" value="es"' in html and 'name="region" value="CO"' in html
    assert 'id="form-apify"' in html and "Reseñas de Amazon" in html and "Comentarios de TikTok" in html
    assert f"/cliente/acme/nicho/{eid}/recolectar/apify/estimar" in html and "Traer (se cobra)" in html
    assert "(falta " not in html


@pytest.fixture()
def llaves_inv(monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "t")
    monkeypatch.setenv("YOUTUBE_API_KEY", "k")
    for v in ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT"):
        monkeypatch.delenv(v, raising=False)


def test_estimar_investigacion_json_y_errores(app, llaves_inv):
    from nicho import datos
    eid = datos.crear_estudio("acme", "X", tema="pantuflas", pais="SE")
    c = app["c"]
    r = c.get(f"/cliente/acme/nicho/{eid}/investigacion/estimar?pais=SE&plataformas=amazon&plataformas=tiktok_shop&redes=youtube&consultas=2")
    d = r.get_json()
    assert r.status_code == 200 and [f["clave"] for f in d["filas"]] == ["amazon", "tiktok_shop"] and d["redes"] == ["youtube"]
    assert d["topes"]["consultas"] == 2 and d["texto"].startswith("US$") and d["filas"][0]["busqueda_texto"].startswith("US$")
    assert c.get(f"/cliente/acme/nicho/{eid}/investigacion/estimar?pais=SE&plataformas=amazon,tiktok_shop").get_json()["plataformas"] == ["amazon", "tiktok_shop"]
    r = c.get(f"/cliente/acme/nicho/{eid}/investigacion/estimar?pais=SE&plataformas=meli")                              # MELI no está en Suecia: busca en México
    assert r.status_code == 200 and (r.get_json()["filas"][0]["mercado"], r.get_json()["filas"][0]["sitio"]) == ("otro", "MX")
    assert c.get(f"/cliente/acme/nicho/{eid}/investigacion/estimar?pais=ZZ&plataformas=amazon").status_code == 400
    assert c.get(f"/cliente/acme/nicho/{eid}/investigacion/estimar?pais=SE").status_code == 400                        # nada elegido
    assert c.get(f"/cliente/acme/nicho/{eid}/investigacion/estimar?pais=SE&redes=reddit").status_code == 400          # red sin llave
    assert c.get("/cliente/acme/nicho/999/investigacion/estimar?pais=SE&plataformas=amazon").status_code == 404


def test_iniciar_investigacion_con_el_costo_visto(app, llaves_inv, monkeypatch):
    from nicho import datos, investigacion as inv
    from tareas import investigacion as ti
    eid = datos.crear_estudio("acme", "X", tema="pantuflas para dolor de pies", pais="CO")
    encolados = []
    monkeypatch.setattr(ti.trabajos, "encolar", lambda job_id, tipo, payload, **kw: encolados.append((job_id, tipo, payload)) or True)
    estimado = inv.estimar({}, "SE", ["amazon"], ["youtube"], inv.TOPES_DEFECTO)
    forma = {"pais": "SE", "plataformas": ["amazon"], "redes": ["youtube"], "consultas": "3", "productos_por_consulta": "20",
             "productos_elegidos": "15", "resenas_por_producto": "100"}
    r = app["c"].post(f"/cliente/acme/nicho/{eid}/investigacion", data={**forma, "total_visto": "0.01"}, follow_redirects=True)
    assert "vuelve a confirmar" in r.data.decode() and encolados == [] and datos.investigacion("acme", eid) == {}
    r = app["c"].post(f"/cliente/acme/nicho/{eid}/investigacion", data={**forma, "total_visto": str(estimado["total_usd"])})
    assert r.status_code == 302
    i = datos.investigacion("acme", eid)
    assert i["aprobado_usd"] == estimado["total_usd"] and i["plataformas"] == ["amazon"] and i["redes"] == ["youtube"] and i["pais"] == "SE"
    assert datos.estudio("acme", eid)["pais"] == "SE"                                                    # el país elegido queda en el estudio
    assert encolados == [(datos.job_id_inv("acme", eid, "consultas"), "nicho_inv_consultas", {"cliente": "acme", "estudio_id": eid})]
    r = app["c"].post(f"/cliente/acme/nicho/{eid}/investigacion", data={**forma, "total_visto": str(estimado["total_usd"])}, follow_redirects=True)
    assert "en curso" in r.data.decode() and len(encolados) == 1                                        # una viva a la vez
    sin_tema = datos.crear_estudio("acme", "Y", pais="SE")
    r = app["c"].post(f"/cliente/acme/nicho/{sin_tema}/investigacion", data={**forma, "total_visto": "99"}, follow_redirects=True)
    assert "Qué investigar" in r.data.decode() and datos.investigacion("acme", sin_tema) == {}


def test_reanudar_y_cancelar(app, llaves_inv, monkeypatch):
    from nicho import datos, investigacion as inv
    from tareas import investigacion as ti
    eid = datos.crear_estudio("acme", "X", tema="t", pais="SE")
    encolados = []
    monkeypatch.setattr(ti.trabajos, "encolar", lambda job_id, tipo, payload, **kw: encolados.append((job_id, tipo, payload)) or True)
    i = inv.crear_inicial("t", "SE", ["amazon"], [], inv.TOPES_DEFECTO, estimado={"total_usd": 2.0})
    i = inv.marcar_paso(inv.marcar_paso({**i, "consultas": ["a", "b"]}, "consultas", "hecho"), "buscar:amazon", "en_curso")
    datos.iniciar_investigacion("acme", eid, {**i, "estado": "interrumpida"})
    app["c"].post(f"/cliente/acme/nicho/{eid}/investigacion/reanudar")
    assert encolados[-1][1] == "nicho_inv_buscar" and datos.investigacion("acme", eid)["estado"] == "buscando"
    app["c"].post(f"/cliente/acme/nicho/{eid}/investigacion/cancelar")
    i = datos.investigacion("acme", eid)
    assert i["estado"] == "detenida" and i["detenida_por"] == "cancelada"
    r = app["c"].post(f"/cliente/acme/nicho/{eid}/investigacion/cancelar", follow_redirects=True)
    assert "No hay investigación en curso" in r.data.decode()


def test_pagina_con_la_investigacion(app, llaves_inv, monkeypatch):
    from nicho import datos, investigacion as inv, rutas
    eid = datos.crear_estudio("acme", "X", tema="t", pais="CO")
    html = app["c"].get(f"/cliente/acme/nicho/{eid}").data.decode()
    assert 'id="form-investigar"' in html and 'name="plataformas" value="meli"' in html and 'data-paises="*"' in html
    assert f"/cliente/acme/nicho/{eid}/investigacion/estimar" in html and 'name="total_visto"' in html and '<option value="CO" selected' in html
    i = inv.crear_inicial("t", "CO", ["meli"], [], inv.TOPES_DEFECTO, estimado={"total_usd": 2.0})
    i = inv.marcar_paso(inv.marcar_paso({**i, "consultas": ["pantuflas"]}, "consultas", "hecho", usd=0.01), "buscar:meli", "en_curso")
    datos.iniciar_investigacion("acme", eid, i)
    monkeypatch.setattr(rutas.trabajos, "en_curso", lambda job: job == datos.job_id_inv("acme", eid, "buscar:meli"))
    html = app["c"].get(f"/cliente/acme/nicho/{eid}").data.decode()
    assert f'data-poll-job="{datos.job_id_inv("acme", eid, "buscar:meli")}"' in html and "<script>iniciarPolling" not in html
    assert "buscar en Mercado Libre" in html and "pantuflas" in html and "Cancelar" in html and 'id="form-investigar"' not in html
    datos.guardar_productos_nicho("acme", eid, "meli", [{"fuente_id": "MCO1", "titulo": "Pantuflas ortopédicas", "n_resenas": 40, "url": "https://x/1"}])
    datos.actualizar_investigacion("acme", eid, lambda x: inv.detener(x, "no se encontraron productos del nicho"))
    html = app["c"].get(f"/cliente/acme/nicho/{eid}").data.decode()
    assert "Pantuflas ortopédicas" in html and "no se encontraron productos del nicho" in html and "Reanudar" in html
    assert 'id="form-investigar"' in html                                                              # «Investigar de nuevo» disponible


def test_pais_al_crear_y_editar_estudio(app):
    from nicho import datos
    app["c"].post("/cliente/acme/nicho/estudios", data={"nombre": "Con país", "tema": "t", "pais": "MX"})
    e = [x for x in datos.estudios("acme") if x["nombre"] == "Con país"][0]
    assert e["pais"] == "MX"
    app["c"].post(f"/cliente/acme/nicho/{e['id']}/editar", data={"nombre": "Con país", "pais": "SE"})
    assert datos.estudio("acme", e["id"])["pais"] == "SE"
    r = app["c"].post(f"/cliente/acme/nicho/{e['id']}/editar", data={"nombre": "Con país", "pais": "ZZ"}, follow_redirects=True)
    assert "País no soportado" in r.data.decode() and datos.estudio("acme", e["id"])["pais"] == "SE"
    html = app["c"].get("/cliente/acme").data.decode()
    assert 'name="pais"' in html


def test_manual_espera_mientras_la_investigacion_esta_viva(app, llaves):
    """Ruling 13 (lado rutas): los botones manuales de recolección/generación
    encolan con el MISMO job_id que un paso de la cadena (`resenas:*`,
    `redes:*`, `generar`) -- si se dejaran encolar mientras la investigación
    corre, el paso de la cadena no podría encolarse y quedaría `interrumpida`
    (Task 5). Las rutas deben rehusarse ANTES de intentarlo."""
    from nicho import datos, investigacion as inv
    eid = datos.crear_estudio("acme", "X", tema="t", pais="SE")
    datos.agregar_comentarios("acme", eid, "texto", [{"fuente_id": f"c{i}", "texto": f"Comentario {i}: pesa mucho"} for i in range(25)])
    i = inv.crear_inicial("t", "SE", ["amazon"], [], inv.TOPES_DEFECTO, estimado={"total_usd": 2.0})
    datos.iniciar_investigacion("acme", eid, i)
    c = app["c"]
    for fuente, datos_forma in (("reddit", {"palabras_clave": "x"}), ("youtube", {"palabras_clave": "x"}), ("apify", {})):
        r = c.post(f"/cliente/acme/nicho/{eid}/recolectar/{fuente}", data=datos_forma, follow_redirects=True)
        assert "espera a que termine o cancélala" in r.data.decode(), fuente
    assert app["encolados"] == []
    r = c.post(f"/cliente/acme/nicho/{eid}/generar", follow_redirects=True)
    assert "espera a que termine o cancélala" in r.data.decode() and app["encolados"] == []
    c.post(f"/cliente/acme/nicho/{eid}/comentarios/texto", data={"texto": "Gotea mucho el envase", "modo": "lineas"})
    assert datos.estudio("acme", eid)["comentarios_total"] == 26                     # texto sigue funcionando
    datos.actualizar_investigacion("acme", eid, lambda x: {**x, "estado": "lista"})  # como antes, en cuanto termina
    r = c.post(f"/cliente/acme/nicho/{eid}/recolectar/reddit", data={"palabras_clave": "x"}, follow_redirects=True)
    assert "espera a que termine o cancélala" not in r.data.decode() and app["encolados"]
    r = c.post(f"/cliente/acme/nicho/{eid}/generar", follow_redirects=True)
    assert "espera a que termine o cancélala" not in r.data.decode()


def test_solo_mismo_origen_bloquea_post_de_otro_sitio(app, llaves_inv, monkeypatch):
    """Ruling 18: el Blueprint nicho también gasta dinero por POST y le
    faltaba la barrera CSRF que ya tienen Flow Plus/Sprints/Triple Whale/el
    editor."""
    from nicho import datos, investigacion as inv
    from tareas import investigacion as ti
    eid = datos.crear_estudio("acme", "X", tema="t", pais="SE")
    encolados = []
    monkeypatch.setattr(ti.trabajos, "encolar", lambda job_id, tipo, payload, **kw: encolados.append((job_id, tipo, payload)) or True)
    estimado = inv.estimar({}, "SE", ["amazon"], [], inv.TOPES_DEFECTO)
    forma = {"pais": "SE", "plataformas": ["amazon"], "total_visto": str(estimado["total_usd"])}
    r = app["c"].post(f"/cliente/acme/nicho/{eid}/investigacion", data=forma, headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403 and encolados == [] and datos.investigacion("acme", eid) == {}
    r = app["c"].post(f"/cliente/acme/nicho/{eid}/investigacion", data=forma, headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 302 and encolados
    eid2 = datos.crear_estudio("acme", "Y", tema="t", pais="SE")
    r = app["c"].post(f"/cliente/acme/nicho/{eid2}/investigacion", data=forma)      # sin cabecera, como manda el test client
    assert r.status_code == 302


def test_avatares_del_proyecto_pagina_y_pestana(app):
    from nicho import datos
    from sprints import datos as sd
    eid, sid = _con_avatares(datos)
    pid = sd.crear_persona("acme", "Premium", resumen="Quiere lo mejor")
    c = app["c"]
    html = c.get("/cliente/acme/nicho/avatares").data.decode()
    assert "Nuevos (sin aprobar)" in html and "Aprobados" in html and "Premium" in html and SUB["nombre"] in html
    assert f'id="avatar-a{sid}"' in html and f'id="avatar-p{pid}"' in html and "incompleto: falta" in html
    assert f"/cliente/acme/nicho/persona/{pid}/ficha" in html and 'id="nuevo-avatar"' in html
    assert 'action="/cliente/acme/nicho/avatares/nuevo"' in html and 'name="volver" value="lista"' in html
    tab = c.get("/cliente/acme").data.decode()
    assert "/cliente/acme/nicho/avatares" in tab and "Aprobados: 1" in tab and "Nuevos por revisar: 1" in tab
    assert "Citas textuales" not in tab                                         # nada de fichas en la página del proyecto


def test_crear_avatar_a_mano_y_editar_sincroniza(app):
    from nicho import datos
    from sprints import datos as sd
    c = app["c"]
    r = c.post("/cliente/acme/nicho/avatares/nuevo", data={"nombre": "Marta / La que camina", "deseo": "Quiero caminar sin dolor", "base": "emocion"})
    assert r.status_code == 302 and "/cliente/acme/nicho/avatares" in r.headers["Location"] and "#avatar-a" in r.headers["Location"]
    aid = int(r.headers["Location"].split("#avatar-a")[1])
    a = datos.avatar("acme", aid)
    p = sd.persona("acme", a["persona_id"])
    assert a["estado"] == "aprobado" and p["origen"] == "manual" and p["nombre"] == "Marta / La que camina"
    r = c.post(f"/cliente/acme/nicho/avatar/{aid}/editar", data={"nombre": "Marta / La que camina", "tono": "Cálido", "volver": "lista"},
               follow_redirects=True)
    assert "la persona que usa la app se actualizó" in r.data.decode() and sd.persona("acme", a["persona_id"])["tono"] == "Cálido"
    r = c.post("/cliente/acme/nicho/avatares/nuevo", data={"nombre": " "}, follow_redirects=True)
    assert "necesita un nombre" in r.data.decode()


def test_aprobar_incompleto_avisa_y_vuelve_al_estudio(app):
    from nicho import datos
    eid, sid = _con_avatares(datos)
    r = app["c"].post(f"/cliente/acme/nicho/avatar/{sid}/aprobar")
    assert r.headers["Location"].endswith(f"/nicho/{eid}")
    r = app["c"].get(f"/cliente/acme/nicho/{eid}")
    assert datos.avatar("acme", sid)["estado"] == "aprobado"
    r = app["c"].post(f"/cliente/acme/nicho/avatar/{sid}/descartar", data={"volver": "lista"})
    assert "/cliente/acme/nicho/avatares" in r.headers["Location"]


def test_persona_sin_avatar_ficha_y_archivar(app):
    """Ruling 21 (nicho.persona_archivar): con un avatar detrás -- aquí, el
    que «Editar ficha» le acaba de crear -- esta ruta ya no archiva a `pid`
    (se usa el Aprobar/Descartar de su ficha); una persona genuinamente sin
    avatar (`pid_sola`) se archiva/desarchiva como siempre."""
    from nicho import datos
    from sprints import datos as sd
    pid = sd.crear_persona("acme", "Premium", resumen="Quiere lo mejor")
    pid_sola = sd.crear_persona("acme", "Básica", resumen="Solo lo esencial")
    c = app["c"]
    r = c.post(f"/cliente/acme/nicho/persona/{pid}/ficha")
    aid = int(r.headers["Location"].split("#avatar-a")[1])
    assert datos.avatar("acme", aid)["persona_id"] == pid and "abrir=a" in r.headers["Location"]
    c.post(f"/cliente/acme/nicho/persona/{pid_sola}/archivar")
    assert sd.persona("acme", pid_sola)["archivada"] is True
    c.post(f"/cliente/acme/nicho/persona/{pid_sola}/archivar", data={"desarchivar": "1"})
    assert sd.persona("acme", pid_sola)["archivada"] is False
    assert c.post("/cliente/acme/nicho/persona/999/ficha", follow_redirects=True).status_code == 200
    assert c.post("/cliente/acme/nicho/persona/999/archivar").status_code == 404


def test_persona_archivar_rechaza_si_tiene_avatar(app):
    """Ruling 21: cualquier avatar de este cliente enlazado a la persona
    (incluido el que crea «Editar ficha», y el de una aprobada de verdad)
    bloquea esta ruta con un aviso -- nada cambia -- porque la plantilla solo
    ofrece Archivar/Desarchivar cuando la persona no tiene avatar (para las
    que sí, `acciones_avatar` ya trae Aprobar/Descartar)."""
    from nicho import datos
    from sprints import datos as sd
    pid = sd.crear_persona("acme", "Premium", resumen="Quiere lo mejor")
    c = app["c"]
    c.post(f"/cliente/acme/nicho/persona/{pid}/ficha")
    r = c.post(f"/cliente/acme/nicho/persona/{pid}/archivar", follow_redirects=True)
    assert "descártalo desde su ficha" in r.data.decode() and sd.persona("acme", pid)["archivada"] is False
    eid, sid = _con_avatares(datos)
    datos.aprobar_avatar("acme", sid)
    pid2 = datos.avatar("acme", sid)["persona_id"]
    c.post(f"/cliente/acme/nicho/persona/{pid2}/archivar")
    assert sd.persona("acme", pid2)["archivada"] is False
    assert c.post("/cliente/acme/nicho/persona/999/archivar").status_code == 404


def test_completar_desde_el_estudio_con_el_costo_visto(app):
    import gastos
    from nicho import avatares, datos
    eid, sid = _con_avatares(datos)
    e = avatares.estimar_completar("acme", eid)
    html = app["c"].get(f"/cliente/acme/nicho/{eid}").data.decode()
    assert "incompleto: falta" in html and f"/cliente/acme/nicho/{eid}/completar" in html and gastos.formatear(e["usd"]) in html
    assert "<script>iniciarPolling" not in html
    n = e["avatares"]
    assert (f"Completar {n} incompleto ·" if n == 1 else f"Completar {n} incompletos ·") in html               # plural bien puesto (ola final)
    r = app["c"].post(f"/cliente/acme/nicho/{eid}/completar", data={"total_visto": "0"}, follow_redirects=True)
    assert "vuelve a confirmar" in r.data.decode() and app["encolados"] == []
    app["c"].post(f"/cliente/acme/nicho/{eid}/completar", data={"total_visto": str(e["usd"])})
    assert app["encolados"][-1]["tipo"] == "nicho_completar_avatares" and app["encolados"][-1]["max_intentos"] == 1


def test_chips_de_avatares_no_se_cortan_en_el_celular(app):
    """Ruling 25 (fix round 1): `.tag-estado` es `white-space: nowrap` y este
    task es el primero en meterle texto libre y largo -- sin overrides scoped
    se corta en silencio contra el borde del celular (`body` ya tiene
    `overflow-x: hidden`). No se toca `.tag-estado` global: sus otros usos
    son etiquetas cortas que sí deben quedar en una sola línea."""
    import re
    from nicho import datos
    from sprints import datos as sd
    css = open("static/style.css", encoding="utf-8").read()
    faltantes = re.search(r"\.nicho-faltantes \{[^}]*\}", css)
    assert faltantes, "falta la regla .nicho-faltantes en static/style.css"
    assert "white-space: normal" in faltantes.group(0) and "overflow-wrap: anywhere" in faltantes.group(0) and "max-width: 100%" in faltantes.group(0)
    muestra = re.search(r"\.nicho-avatares-muestra a \{[^}]*\}", css)
    assert muestra, "falta la regla .nicho-avatares-muestra a en static/style.css"
    assert "max-width: 100%" in muestra.group(0) and "overflow: hidden" in muestra.group(0) and "text-overflow: ellipsis" in muestra.group(0)
    eid, sid = _con_avatares(datos)
    pid = sd.crear_persona("acme", "Premium", resumen="Quiere lo mejor")
    tab = app["c"].get("/cliente/acme").data.decode()
    assert f'title="{SUB["nombre"]}"' in tab and 'title="Premium"' in tab
    lista = app["c"].get("/cliente/acme/nicho/avatares").data.decode()
    assert 'class="tag-estado sprint-aviso nicho-faltantes"' in lista


def test_estudio_oculto_no_se_abre_como_estudio(app):
    """Ruling 26 (fix round 1): el estudio oculto de los avatares escritos a
    mano no tiene comentarios que revisar ni acciones de estudio que
    apliquen -- typear su URL manda a la lista del proyecto, no a su
    página."""
    from nicho import datos
    eid, _nid = datos.estudio_manual("acme")
    r = app["c"].get(f"/cliente/acme/nicho/{eid}")
    assert r.status_code == 302 and r.headers["Location"].endswith("/cliente/acme/nicho/avatares")
    assert app["c"].get("/cliente/acme/nicho/999999").status_code == 404


def test_cliente_sin_apify_no_ve_plataformas_ni_variables_del_env(app, monkeypatch):
    """Ruling 19: sin APIFY_TOKEN, un cliente no ve en la tarjeta las
    plataformas que lo necesitan (amazon/meli/tiktok_shop) ni el nombre de la
    variable ni «Falta …»; un pedido a mano para esa plataforma responde el
    mensaje neutro, tanto en el estimado como al intentar iniciar."""
    from nicho import datos
    monkeypatch.delenv("APIFY_TOKEN", raising=False)
    eid = datos.crear_estudio("acme", "X", tema="t", pais="US")
    c = app["dashboard"].app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "user_acme"; s["rol"] = "cliente"; s["cliente"] = "acme"
    html = c.get(f"/cliente/acme/nicho/{eid}").data.decode()
    assert 'name="plataformas" value="amazon"' not in html and 'name="plataformas" value="meli"' not in html
    assert 'name="plataformas" value="tiktok_shop"' not in html
    assert "APIFY_TOKEN" not in html and "(falta " not in html
    r = c.get(f"/cliente/acme/nicho/{eid}/investigacion/estimar?plataformas=amazon")
    assert r.status_code == 400 and r.get_json()["error"] == "Esa fuente no está disponible todavía."
    r = c.post(f"/cliente/acme/nicho/{eid}/investigacion", data={"plataformas": "amazon", "total_visto": "99"}, follow_redirects=True)
    assert "Esa fuente no está disponible todavía." in r.data.decode()
    assert datos.investigacion("acme", eid) == {}


def test_pagina_muestra_las_busquedas_por_idioma(app, llaves_inv):
    from nicho import datos, investigacion as inv
    eid = datos.crear_estudio("acme", "X", tema="t", pais="CO")
    i = inv.crear_inicial("t", "CO", ["meli", "walmart"], [], inv.TOPES_DEFECTO, estimado={"total_usd": 2.0})
    i = inv.marcar_paso({**i, "consultas": ["botella con horario"],
                         "consultas_por_idioma": {"es": ["botella con horario"], "en": ["water bottle time marker"]}}, "consultas", "hecho")
    datos.iniciar_investigacion("acme", eid, i)
    html = app["c"].get(f"/cliente/acme/nicho/{eid}").data.decode()
    linea = html.split("Búsquedas:")[1].split("</p>")[0]
    assert "botella con horario" in linea and "<small>(inglés)</small>" in linea and "water bottle time marker" in linea
    assert "(español)" not in linea and "<small>(en)</small>" not in linea       # las del país no se repiten; el idioma, con su nombre


def _chip(html, clave):
    """Lo que sigue a `value="<clave>"` dentro de su <input> (atributos)."""
    return html.split(f'value="{clave}"')[1].split(">")[0]


def _grupo(html, id_):
    return html.split(f'id="{id_}"')[1].split("</fieldset>")[0]


def test_tiendas_agrupadas_por_mercado(app, llaves_inv):
    from nicho import datos, investigacion as inv
    eid = datos.crear_estudio("acme", "X", tema="t", pais="CO")
    html = app["c"].get(f"/cliente/acme/nicho/{eid}").data.decode()
    locales, otras = _grupo(html, "inv-tiendas-locales"), _grupo(html, "inv-tiendas-otras")
    assert "Tiendas de Colombia" in locales and "De otros mercados" in otras
    for clave in ("meli", "tiktok_shop", "aliexpress"):
        assert f'value="{clave}"' in locales and f'value="{clave}"' not in otras and " checked" in _chip(locales, clave)
    for clave in ("amazon", "walmart"):
        assert f'value="{clave}"' in otras and f'value="{clave}"' not in locales and " checked" not in _chip(otras, clave)
    assert "(Estados Unidos)" in otras and 'data-orden="0"' in _chip(otras, "amazon")
    assert 'id="inv-marcar-todas"' in html and "Marcar todas" in html
    r = app["c"].get(f"/cliente/acme/nicho/{eid}/investigacion/estimar?pais=CO&plataformas=meli&plataformas=walmart")
    assert r.status_code == 200 and [f["etiqueta"] for f in r.get_json()["filas"]] == ["Mercado Libre", "Walmart (Estados Unidos)"]
    eid_us = datos.crear_estudio("acme", "Y", tema="t", pais="US")
    html = app["c"].get(f"/cliente/acme/nicho/{eid_us}").data.decode()
    locales, otras = _grupo(html, "inv-tiendas-locales"), _grupo(html, "inv-tiendas-otras")
    assert all(f'value="{c}"' in locales for c in ("amazon", "walmart", "tiktok_shop", "aliexpress"))
    assert 'value="meli"' in otras and "(México)" in otras
    # la tabla de productos: nombre de la tienda y, sin número de reseñas, los vendidos
    datos.iniciar_investigacion("acme", eid, inv.crear_inicial("t", "CO", ["aliexpress"], [], inv.TOPES_DEFECTO, estimado={"total_usd": 1.0}))
    datos.guardar_productos_nicho("acme", eid, "aliexpress", [{"fuente_id": "3256806541493299", "titulo": "Botella 1L", "n_resenas": None,
                                                                "extra": {"vendidos": 4025}, "url": "https://www.aliexpress.com/item/3256806541493299.html"}])
    html = app["c"].get(f"/cliente/acme/nicho/{eid}").data.decode()
    tabla = html.split('class="tabla-apilada nicho-inv-tabla"')[1].split("</table>")[0]
    assert "<td>AliExpress</td>" in tabla and "4025 vendidos" in tabla
    datos.guardar_productos_nicho("acme", eid, "aliexpress", [{"fuente_id": "1005", "titulo": "Botella 2L", "n_resenas": None,
                                                                "extra": {"vendidos": 1}, "url": "https://www.aliexpress.com/item/1005.html"}])
    tabla = app["c"].get(f"/cliente/acme/nicho/{eid}").data.decode().split('class="tabla-apilada nicho-inv-tabla"')[1].split("</table>")[0]
    assert "1 vendido</small>" in tabla and "1 vendidos" not in tabla and "4025 vendidos" in tabla      # singular (ola final B7)


def test_comentarios_y_citas_de_otro_mercado_llevan_su_pais(app, llaves_inv, monkeypatch):
    from nicho import datos
    eid = datos.crear_estudio("acme", "Botellas", producto="Botella", tema="t", pais="CO")
    datos.agregar_comentarios("acme", eid, "walmart", [
        {"fuente_id": "w1", "texto": "la garrafa pesa demasiado, I returned it", "extra": {"producto": "1", "plataforma": "walmart", "pais": "US", "mercado": "otro"}},
        {"fuente_id": "w2", "texto": "Too heavy for me", "extra": {"producto": "1", "plataforma": "walmart", "pais": "PL", "mercado": "otro"}}])
    datos.agregar_comentarios("acme", eid, "meli", [{"fuente_id": "m1", "texto": "Me encanta la botella", "extra": {"pais": "CO", "mercado": "local"}}])
    ids = {c["fuente_id"]: c["id"] for c in datos.comentarios_para_generar("acme", eid)}
    assert datos.paises_otro_mercado_de("acme", [ids["w1"], ids["w2"], ids["m1"]]) == {ids["w1"]: "US", ids["w2"]: "PL"}
    assert datos.paises_otro_mercado_de("acme", [ids["w1"], ids["m1"]]) == {ids["w1"]: "US"} and datos.paises_otro_mercado_de("acme", []) == {}
    html = app["c"].get(f"/cliente/acme/nicho/{eid}").data.decode()
    assert "otro mercado: Estados Unidos" in html and "otro mercado: PL" in html and html.count("otro mercado:") == 2
    sub = {**SUB, "evidencia": [{"comentario_id": ids["w1"], "cita": "la garrafa pesa demasiado"}]}
    datos.guardar_generacion("acme", eid, [{"nombre": "Sin peso", "deseo": "Quiero", "resumen": "r", "sub_avatares": [sub]}])
    pedidos, real = [], datos.paises_otro_mercado_de
    monkeypatch.setattr(datos, "paises_otro_mercado_de", lambda cliente, lista: pedidos.append(list(lista)) or real(cliente, lista))
    html = app["c"].get(f"/cliente/acme/nicho/{eid}").data.decode()
    assert "otro mercado: Estados Unidos" in html.split("«la garrafa pesa demasiado»")[1].split("</blockquote>")[0]
    assert pedidos == [[ids["w1"]]]                       # la página solo mira el extra de los comentarios citados (ola final B6)
    html = app["c"].get("/cliente/acme/nicho/avatares").data.decode()
    assert "otro mercado: Estados Unidos" in html.split("«la garrafa pesa demasiado»")[1].split("</blockquote>")[0]
