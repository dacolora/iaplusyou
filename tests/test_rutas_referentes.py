"""Rutas del Blueprint referentes: grid y ficha como fragmentos; visibilidad por cliente."""
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
    productos = [{"id": "espejo_led", "nombre": "Espejo LED", "descripcion": "redondo",
                 "representativa_url": "https://r2/e.jpg", "regla": "Reprodúcelo idéntico: marco negro mate.",
                 "referencias": ["/x/a.jpg", "/x/b.jpg"]}]
    monkeypatch.setattr(catalogo_productos, "listar", lambda c, cat="producto": productos)
    monkeypatch.setattr(catalogo_productos, "encontrar",
                        lambda c, pid, categoria=None: next((p for p in productos if p["id"] == pid), None))
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    (tmp_path / "clientes" / "acme").mkdir(parents=True)
    (tmp_path / "clientes" / "otro").mkdir(parents=True)
    return {"dashboard": dashboard, "c": _cliente_admin(dashboard), "productos": productos}


def _anuncio(aid, **extra):
    base = {"anuncio_id": aid, "pagina_id": "1", "fuente": "copycoders", "marca": "Lulutox Tea",
            "url_anuncio": f"https://www.facebook.com/ads/library/?id={aid}", "titular": f"Titular {aid}", "idioma": "en",
            "tipo": "imagen", "imagen_origen": "https://cdn/x.jpg", "dias": 10, "variantes": 2, "activo": True,
            "etapa": "BOF", "consciencia": "most-aware", "familia": "Price Slash Hero", "dolor": "ninguno-oferta",
            "firma": "Firma en español", "clasificacion": "fuente", "extra": {}}
    base.update(extra)
    return base


def _sembrar(cliente=None):
    from referentes import datos
    datos.familia_asegurar("Price Slash Hero", "Precio tachado en grande.")
    ids = []
    for i in range(3):
        rid, _ = datos.guardar_referente(_anuncio(str(i), etapa="TOF" if i else "BOF"), cliente=cliente)
        datos.marcar_imagen(rid, "ok", f"https://r2/referentes/{i}.jpg")
        ids.append(rid)
    return ids


def test_grid_modo_seleccion_con_campana(app):
    _sembrar()
    c = app["c"]
    r = c.get("/cliente/acme/referentes/grid?campana=7")
    assert r.status_code == 200
    assert b'name="referente_ids"' in r.data
    assert b'type="checkbox"' in r.data


def test_grid_sin_campana_no_muestra_checkboxes(app):
    _sembrar()
    c = app["c"]
    r = c.get("/cliente/acme/referentes/grid")
    assert r.status_code == 200
    assert b'name="referente_ids"' not in r.data


def test_grid_filtra_y_pagina(app):
    _sembrar()
    c = app["c"]
    html = c.get("/cliente/acme/referentes/grid").data.decode()
    assert html.count("ref-tarjeta") >= 3 and "Titular 2" in html and "Mostrar más" not in html
    html = c.get("/cliente/acme/referentes/grid?etapa=TOF").data.decode()
    assert "Titular 0" not in html and "Titular 1" in html
    html = c.get("/cliente/acme/referentes/grid?por_pagina=2").data.decode()
    assert "Mostrar más" in html and 'data-siguiente="2"' in html
    html = c.get("/cliente/acme/referentes/grid?por_pagina=2&pagina=2").data.decode()
    assert html.count("ref-tarjeta") >= 1 and "Mostrar más" not in html
    assert "abajo del funnel" in c.get("/cliente/acme/referentes/grid?etapa=BOF").data.decode()


def test_ficha_y_visibilidad(app):
    from referentes import datos
    ids = _sembrar()
    privado, _ = datos.guardar_referente(_anuncio("99"), cliente="otro")
    datos.marcar_imagen(privado, "ok", "https://r2/referentes/99.jpg")
    c = app["c"]
    html = c.get(f"/cliente/acme/referentes/{ids[0]}/ficha").data.decode()
    assert "Firma en español" in html and "Precio tachado en grande." in html and "facebook.com/ads/library" in html
    assert "muy consciente" in html and "Lulutox Tea" in html
    assert c.get(f"/cliente/acme/referentes/{privado}/ficha").status_code == 404
    assert c.get(f"/cliente/otro/referentes/{privado}/ficha").status_code == 200
    assert "Titular 99" not in c.get("/cliente/acme/referentes/grid").data.decode()


def test_pestana_en_pagina_del_proyecto(app):
    _sembrar()
    c = app["c"]
    html = c.get("/cliente/acme").data.decode()
    assert 'data-tab="referentes"' in html and 'id="tab-referentes"' in html and "Price Slash Hero" in html
    assert "Todas las familias" in html and "Solo míos" in html      # el conteo lo pinta el grid por fetch


def test_cliente_sin_permiso_no_entra(app):
    c = app["dashboard"].app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "otro"; s["rol"] = "cliente"; s["cliente"] = "otro"
    r = c.get("/cliente/acme/referentes/grid")
    assert r.status_code == 302 and "/cliente/otro" in r.headers["Location"]


def test_admin_referentes_importar(app, monkeypatch):
    from referentes import datos
    from tareas import referentes as tr
    c = app["c"]
    llamadas = []
    monkeypatch.setattr(tr.trabajos, "encolar", lambda job_id, tipo, payload, **kw: llamadas.append(payload) or True)
    monkeypatch.setattr(tr.trabajos, "en_curso", lambda job_id: False)
    html = c.get("/admin/referentes").data.decode()
    assert "Importar" in html and "nunca" in html
    r = c.post("/admin/referentes/importar", data={}, headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/admin/referentes")
    assert llamadas[0]["url"] == tr.copycoders.URL_SWIPE and llamadas[0]["fase"] == "anuncios"
    b = datos.barridos(None, "copycoders")[0]
    assert b["pedido_por"] == "admin" and b["consulta"]["url"] == tr.copycoders.URL_SWIPE
    r = c.post("/admin/referentes/importar", data={"url": "https://malo.example/x"}, headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 302 and len(llamadas) == 1
    datos.actualizar_barrido(b["id"], estado="listo", traidos=5587, nuevos=5587, con_imagen=5580)
    html = c.get("/admin/referentes").data.decode()
    assert "5587" in html and "5580" in html


def test_admin_referentes_solo_admin(app):
    c = app["dashboard"].app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "otro"; s["rol"] = "cliente"; s["cliente"] = "otro"
    assert c.get("/admin/referentes").status_code == 302
    assert c.post("/admin/referentes/importar", data={}, headers={"Sec-Fetch-Site": "same-origin"}).status_code == 302


def test_recrear_formulario_precio_y_prompt(app):
    from referentes import datos
    ids = _sembrar()
    c = app["c"]
    html = c.get(f"/cliente/acme/referentes/{ids[0]}/recrear").data.decode()
    assert "Espejo LED" in html and 'selected' in html
    assert "Image 1" in html and "Image 2 y 3" in html and "Titular 0" in html
    assert "Generar imagen" in html and "Como video" in html and "Adaptar con IA" in html
    html_video = c.get(f"/cliente/acme/referentes/{ids[0]}/recrear?tipo=video").data.decode()
    assert "Generar video" in html_video and "Cámara fija" in html_video
    assert c.get(f"/cliente/acme/referentes/{ids[0]}/recrear?producto_id=espejo_led").status_code == 200


def test_recrear_sin_productos_lleva_a_catalogo(app, monkeypatch):
    from referentes import datos
    import catalogo_productos
    monkeypatch.setattr(catalogo_productos, "listar", lambda c, cat="producto": [])
    ids = _sembrar()
    html = app["c"].get(f"/cliente/acme/referentes/{ids[0]}/recrear").data.decode()
    assert "Todavía no tienes productos" in html and "Ir a Catálogo" in html


def test_recrear_referente_inexistente_o_sin_imagen_404(app):
    from referentes import datos
    rid, _ = datos.guardar_referente(_anuncio("500"))
    assert app["c"].get(f"/cliente/acme/referentes/{rid}/recrear").status_code == 404
    assert app["c"].get("/cliente/acme/referentes/999999/recrear").status_code == 404


def test_recrear_adaptar_devuelve_json_y_registra_gasto(app, monkeypatch):
    from referentes import datos, recrear
    import gastos
    ids = _sembrar()
    monkeypatch.setattr(recrear, "_llamar",
                        lambda texto, max_tokens: ('{"titular": "SE ACABA HOY", "prompt": "Con Image 1 e Image 2..."}', 150, 40))
    r = app["c"].post(f"/cliente/acme/referentes/{ids[0]}/recrear/adaptar",
                      json={"producto_id": "espejo_led", "titular": "viejo"})
    assert r.status_code == 200
    body = r.get_json()
    assert body == {"titular": "SE ACABA HOY", "prompt": "Con Image 1 e Image 2..."}
    gasto = gastos.historial("acme", limite=1)[0]
    assert gasto["tipo"] == "adaptar_referente" and gasto["usd"] > 0


def test_recrear_adaptar_sin_producto_o_referente_da_error(app, monkeypatch):
    from referentes import datos, recrear
    ids = _sembrar()
    r = app["c"].post(f"/cliente/acme/referentes/{ids[0]}/recrear/adaptar", json={"producto_id": "", "titular": ""})
    assert r.status_code == 400
    assert app["c"].post("/cliente/acme/referentes/999999/recrear/adaptar", json={"producto_id": "espejo_led"}).status_code == 404
    monkeypatch.setattr(recrear, "_llamar", lambda texto, max_tokens: ("no es json", 10, 5))
    r2 = app["c"].post(f"/cliente/acme/referentes/{ids[0]}/recrear/adaptar", json={"producto_id": "espejo_led"})
    assert r2.status_code == 502


def test_recrear_adaptar_falla_pero_registra_lo_gastado(app, monkeypatch):
    from referentes import datos, recrear
    import gastos
    ids = _sembrar()
    monkeypatch.setattr(recrear, "_llamar", lambda texto, max_tokens: ("no es json", 80, 20))
    r = app["c"].post(f"/cliente/acme/referentes/{ids[0]}/recrear/adaptar",
                      json={"producto_id": "espejo_led", "titular": "viejo"})
    assert r.status_code == 502
    gasto = gastos.historial("acme", limite=1)[0]
    assert gasto["tipo"] == "adaptar_referente" and gasto["usd"] > 0


def test_recrear_generar_imagen_crea_sesion_y_lanza(app, monkeypatch):
    from referentes import datos
    import creative_flow
    import flowplus_lanzar
    ids = _sembrar()
    subidos = []
    monkeypatch.setattr("referentes.recrear.r2_uploader.upload_image",
                        lambda local, clave: subidos.append(clave) or f"https://r2/{clave}")
    lanzado = {}
    monkeypatch.setattr(flowplus_lanzar, "lanzar", lambda cliente, cf_id, entry, **kw: lanzado.update(cliente=cliente, cf_id=cf_id, entry=entry) or True)
    r = app["c"].post(f"/cliente/acme/referentes/{ids[0]}/recrear/generar",
                      data={"producto_id": "espejo_led", "formato": "1:1", "titular": "SE ACABA HOY",
                            "prompt": "Anuncio con Image 1 e Image 2...", "tipo": "imagen"})
    assert r.status_code == 302 and "creativeflowplus" in r.headers["Location"]
    cf_id = lanzado["cf_id"]
    entry = creative_flow.cargar("acme")[cf_id]
    assert entry["prompt_relleno"] == "Anuncio con Image 1 e Image 2..." and entry["tipo"] == "imagen"
    assert entry["aspect_ratio"] == "1:1" and entry["referencias_urls"][0] == "https://r2/referentes/0.jpg"
    assert len(entry["referencias_urls"]) == 3 and entry["referente_id"] == ids[0]
    assert entry["modelo"] == "seedream_v5_pro"


def test_recrear_generar_video_usa_preferencias_del_proyecto(app, monkeypatch):
    import creative_flow
    import flowplus_lanzar
    import proyectos
    ids = _sembrar()
    monkeypatch.setattr("referentes.recrear.r2_uploader.upload_image", lambda local, clave: f"https://r2/{clave}")
    monkeypatch.setattr(proyectos, "preferencias_flowplus", lambda c: {**proyectos.DEFAULTS_FLOWPLUS, "duracion_defecto": 12})
    monkeypatch.setattr(proyectos, "preferencias_sonido", lambda c: {"con_sonido": False, "musica_al_crear": ""})
    lanzado = {}
    monkeypatch.setattr(flowplus_lanzar, "lanzar", lambda cliente, cf_id, entry, **kw: lanzado.update(cf_id=cf_id) or True)
    r = app["c"].post(f"/cliente/acme/referentes/{ids[0]}/recrear/generar",
                      data={"producto_id": "espejo_led", "formato": "9:16", "titular": "X", "prompt": "P", "tipo": "video"})
    assert r.status_code == 302
    entry = creative_flow.cargar("acme")[lanzado["cf_id"]]
    assert entry["tipo"] == "video" and entry["modelo"] == "wan3" and entry["duracion_objetivo"] == 12
    assert entry["con_sonido"] is False


def test_recrear_generar_sin_producto_o_prompt_no_crea_nada(app):
    import creative_flow
    ids = _sembrar()
    app["c"].post(f"/cliente/acme/referentes/{ids[0]}/recrear/generar",
                  data={"producto_id": "", "formato": "1:1", "titular": "X", "prompt": "P", "tipo": "imagen"})
    app["c"].post(f"/cliente/acme/referentes/{ids[0]}/recrear/generar",
                  data={"producto_id": "espejo_led", "formato": "1:1", "titular": "X", "prompt": "", "tipo": "imagen"})
    assert creative_flow.cargar("acme") == {}


def test_ficha_tiene_botones_de_recrear_y_usos(app):
    from referentes import datos
    import creative_flow
    ids = _sembrar()
    html = app["c"].get(f"/cliente/acme/referentes/{ids[0]}/ficha").data.decode()
    assert f"/cliente/acme/referentes/{ids[0]}/recrear" in html and "Recrear con mi producto" in html and "Como video" in html
    assert "Usado" not in html
    cf_id = creative_flow.crear("acme", [], ["Espejo LED"], [], "X", 0, "", "A")
    creative_flow.actualizar("acme", cf_id, referente_id=ids[0])
    html2 = app["c"].get(f"/cliente/acme/referentes/{ids[0]}/ficha").data.decode()
    assert "Usado 1 vez" in html2


def test_ficha_tiene_boton_usar_en_sprint(app):
    ids = _sembrar()
    html = app["c"].get(f"/cliente/acme/referentes/{ids[0]}/ficha").data.decode()
    assert f"/cliente/acme/referentes/{ids[0]}/usar_en_sprint" in html and "Usar en sprint" in html
    assert "data-recrear-abrir" in html


def test_usar_en_sprint_lista_campanas_elegibles(app, monkeypatch):
    ids = _sembrar()
    import sprints.datos as sprints_datos
    monkeypatch.setattr(sprints_datos, "sprints", lambda cliente_: [
        {"id": 1, "nombre": "Sprint de octubre", "estado": "planeando",
         "campanas": [{"id": 10, "orden": 0, "funnel": "tof", "persona_nombre": "Melissa"}]},
        {"id": 2, "nombre": "Sprint cerrado", "estado": "completado",
         "campanas": [{"id": 20, "orden": 0, "funnel": "tof", "persona_nombre": "Carlos"}]},
    ])
    r = app["c"].get(f"/cliente/acme/referentes/{ids[0]}/usar_en_sprint")
    assert r.status_code == 200
    assert b"Sprint de octubre" in r.data
    assert b"Sprint cerrado" not in r.data


def test_usar_en_sprint_referente_inexistente_404(app):
    assert app["c"].get("/cliente/acme/referentes/999999/usar_en_sprint").status_code == 404


def test_traer_form_muestra_precio(app, monkeypatch):
    from referentes.fuentes import atria
    monkeypatch.setenv("ATRIA_API_KEY", "atria-sk_test")
    monkeypatch.setattr(atria, "estimar", lambda consulta, tope: {"usd_fuente": 0.0, "llamadas": 4,
                                                                  "detalle": "4 llamadas del plan de Atria"})
    c = app["c"]
    r = c.get("/cliente/acme/referentes/traer?fuente=atria&modo=palabra&palabra=protein&idioma=en&tope=200",
              headers={"X-Requested-With": "fetch"})
    assert r.status_code == 200
    assert b"llamadas del plan de Atria" in r.data
    assert b"Clasificar" in r.data


def test_traer_form_fuente_sin_llave_aparece_apagada(app, monkeypatch):
    monkeypatch.delenv("ATRIA_API_KEY", raising=False)
    c = app["c"]
    r = c.get("/cliente/acme/referentes/traer", headers={"X-Requested-With": "fetch"})
    assert r.status_code == 200
    assert b"ATRIA_API_KEY" in r.data or "no está configurad".encode() in r.data


def test_traer_post_crea_barrido_y_encola(app, monkeypatch):
    from tareas import referentes as tareas_referentes
    monkeypatch.setenv("ATRIA_API_KEY", "atria-sk_test")
    llamadas = []
    monkeypatch.setattr(tareas_referentes, "encolar_barrer", lambda *a, **kw: llamadas.append((a, kw)) or 42)
    c = app["c"]
    r = c.post("/cliente/acme/referentes/traer", data={
        "fuente": "atria", "modo": "palabra", "palabra": "protein", "idioma": "en", "tope": "200",
        "solo_activos": "on",
    }, follow_redirects=False)
    assert r.status_code == 302
    assert llamadas and llamadas[0][0][0] == "acme"


def test_traer_post_tope_excede_2000_se_recorta(app, monkeypatch):
    from tareas import referentes as tareas_referentes
    monkeypatch.setenv("ATRIA_API_KEY", "atria-sk_test")
    llamadas = []
    monkeypatch.setattr(tareas_referentes, "encolar_barrer", lambda *a, **kw: llamadas.append(a) or 1)
    c = app["c"]
    c.post("/cliente/acme/referentes/traer", data={
        "fuente": "atria", "modo": "palabra", "palabra": "x", "idioma": "en", "tope": "999999",
    })
    assert llamadas[0][3] <= 2000  # el 4to posicional de encolar_barrer(cliente, fuente, consulta, tope, ...) es tope


def test_traer_post_sin_marca_ni_palabra_falla(app, monkeypatch):
    monkeypatch.setenv("ATRIA_API_KEY", "atria-sk_test")
    c = app["c"]
    r = c.post("/cliente/acme/referentes/traer", data={"fuente": "atria", "modo": "marca", "tope": "50"},
              follow_redirects=True)
    assert r.status_code == 200


def test_traer_post_fuente_sin_llave_no_encola(app, monkeypatch):
    from tareas import referentes as tareas_referentes
    monkeypatch.delenv("ATRIA_API_KEY", raising=False)
    llamadas = []
    monkeypatch.setattr(tareas_referentes, "encolar_barrer", lambda *a, **kw: llamadas.append(a) or 1)
    c = app["c"]
    r = c.post("/cliente/acme/referentes/traer", data={
        "fuente": "atria", "modo": "palabra", "palabra": "protein", "idioma": "en", "tope": "50",
    }, follow_redirects=False)
    assert r.status_code == 302
    assert not llamadas
