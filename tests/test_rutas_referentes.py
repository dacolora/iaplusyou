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


def test_admin_referentes_traer_muestra_precio(app, monkeypatch):
    monkeypatch.setenv("ATRIA_API_KEY", "atria-sk_test")
    monkeypatch.setattr("referentes.fuentes.atria.estimar", lambda consulta, tope: {"usd_fuente": 0.0, "llamadas": 2, "detalle": "2 llamadas del plan de Atria"})
    c = app["c"]
    html = c.get("/admin/referentes?fuente=atria&modo=palabra&palabra=zapatos&tope=100").data.decode()
    assert "US$" in html
    assert 'name="tope"' in html
    # "Traer y clasificar ≈ US$" solo renderiza dentro de {% if precio_traer %}
    # (el botón de lanzar) -- "US$" solo no basta, aparece también en el texto
    # estático del hero ("≈ US$1 una sola vez") sin importar si hubo precio.
    assert "Traer y clasificar ≈ US$" in html
    # Sin palabra/pagina_id no hay consulta que estimar: precio_traer queda
    # None y el botón de lanzar no debe aparecer -- prueba que el gate arriba
    # de verdad gatea algo, no que el texto esté siempre presente.
    html_sin_consulta = c.get("/admin/referentes").data.decode()
    assert "Traer y clasificar ≈ US$" not in html_sin_consulta


def test_admin_referentes_traer_lanza_barrido_global(app, monkeypatch):
    from referentes import datos
    from tareas import referentes as tr
    monkeypatch.setenv("ATRIA_API_KEY", "atria-sk_test")
    llamadas = []
    monkeypatch.setattr(tr, "encolar_barrer", lambda *a, **kw: llamadas.append((a, kw)) or True)
    c = app["c"]
    r = c.post("/admin/referentes/traer", data={"fuente": "atria", "modo": "palabra", "palabra": "zapatos", "idioma": "es", "tope": "50"},
              headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/admin/referentes")
    assert len(llamadas) == 1
    args, kw = llamadas[0]
    assert args[0] is None            # cliente=None: barrido global
    assert args[1] == "atria"
    assert args[2]["palabra"] == "zapatos"


def test_admin_referentes_traer_sin_fuente_no_lanza(app):
    c = app["c"]
    r = c.post("/admin/referentes/traer", data={"fuente": "no-existe"}, headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 302
    from referentes import datos
    assert datos.barridos(None, "no-existe") == []


def test_admin_referentes_traer_solo_admin(app):
    c = app["dashboard"].app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "otro"; s["rol"] = "cliente"; s["cliente"] = "otro"
    assert c.get("/admin/referentes").status_code == 302
    assert c.post("/admin/referentes/traer", data={}, headers={"Sec-Fetch-Site": "same-origin"}).status_code == 302


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


def test_traer_form_no_lleva_data_recrear_campo(app, monkeypatch):
    """Side bug de Critical 1: `data-recrear-campo` es del formulario «Recrear
    con mi producto» -- su listener delegado en _tab_referentes.html reacciona
    a CUALQUIER elemento con ese atributo, en cualquier formulario cargado en
    el mismo diálogo. Si quedaba copiado acá (como en `formato`), cambiarlo en
    ESTE formulario disparaba el refresco de ESE OTRO contra una URL rota."""
    monkeypatch.setenv("ATRIA_API_KEY", "atria-sk_test")
    html = app["c"].get("/cliente/acme/referentes/traer", headers={"X-Requested-With": "fetch"}).data.decode()
    assert "data-recrear-campo" not in html


def test_traer_form_sin_consulta_ofrece_boton_ver_precio(app, monkeypatch):
    """Critical 1: primera carga sin query params -> sin precio todavía, pero
    con un botón explícito para pedirlo (antes no había nada, ni precio ni
    forma de pedirlo sin tocar un campo)."""
    monkeypatch.setenv("ATRIA_API_KEY", "atria-sk_test")
    html = app["c"].get("/cliente/acme/referentes/traer", headers={"X-Requested-With": "fetch"}).data.decode()
    assert 'id="traer-ver-precio"' in html
    assert "completa los datos para ver el precio" in html.lower()
    assert 'data-precio="' in html


def test_traer_form_pagina_id_con_link_extrae_solo_el_id(app, monkeypatch):
    """Important 2: pegar el link completo del Ad Library en el campo de
    marca (el placeholder invita a hacerlo) debe extraer solo el
    view_all_page_id -- antes se mandaba a Atria tal cual, produciendo una
    ruta rota (`/brand-library/mhttps://...`) y gastando una llamada real
    antes de fallar."""
    from referentes.fuentes import atria
    monkeypatch.setenv("ATRIA_API_KEY", "atria-sk_test")
    llamadas = []
    monkeypatch.setattr(atria, "estimar", lambda consulta, tope: llamadas.append(consulta) or
                        {"usd_fuente": 0.0, "llamadas": 1, "detalle": "1 llamada del plan de Atria"})
    url_pegada = "https://www.facebook.com/ads/library/?active_status=all&view_all_page_id=110811200743559&id=1"
    r = app["c"].get("/cliente/acme/referentes/traer",
                     query_string={"fuente": "atria", "modo": "marca", "pagina_id": url_pegada},
                     headers={"X-Requested-With": "fetch"})
    assert r.status_code == 200
    assert llamadas and llamadas[0]["pagina_id"] == "110811200743559"
    # El campo se re-pinta con el id ya extraído, no con la URL pegada.
    assert 'value="110811200743559"' in r.data.decode()
    assert url_pegada not in r.data.decode()


def test_traer_post_pagina_id_con_link_extrae_solo_el_id(app, monkeypatch):
    from tareas import referentes as tareas_referentes
    monkeypatch.setenv("ATRIA_API_KEY", "atria-sk_test")
    llamadas = []
    monkeypatch.setattr(tareas_referentes, "encolar_barrer", lambda *a, **kw: llamadas.append(a) or 1)
    r = app["c"].post("/cliente/acme/referentes/traer", data={
        "fuente": "atria", "modo": "marca",
        "pagina_id": "https://www.facebook.com/ads/library/?view_all_page_id=110811200743559", "tope": "50",
    }, follow_redirects=False)
    assert r.status_code == 302
    consulta = llamadas[0][2]  # encolar_barrer(cliente, fuente, consulta, tope, ...)
    assert consulta["pagina_id"] == "110811200743559"


def test_traer_post_pagina_id_invalido_no_encola_ni_gasta_llamada(app, monkeypatch):
    """Important 2: un texto que no es ni un id numérico ni un link con
    view_all_page_id se descarta -- nunca llega a `estimar`/`encolar_barrer`
    (que gastaría una llamada real contra Atria antes de fallar)."""
    from referentes.fuentes import atria
    from tareas import referentes as tareas_referentes
    monkeypatch.setenv("ATRIA_API_KEY", "atria-sk_test")
    llamadas_estimar = []
    monkeypatch.setattr(atria, "estimar", lambda consulta, tope: llamadas_estimar.append(consulta) or
                        {"usd_fuente": 0.0, "llamadas": 1, "detalle": "x"})
    llamadas_encolar = []
    monkeypatch.setattr(tareas_referentes, "encolar_barrer", lambda *a, **kw: llamadas_encolar.append(a) or 1)
    r = app["c"].post("/cliente/acme/referentes/traer", data={
        "fuente": "atria", "modo": "marca", "pagina_id": "no es ni un link ni un id", "tope": "50",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert not llamadas_estimar and not llamadas_encolar


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


def test_traer_form_apify_configurada_muestra_pais(app, monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "tok_test")
    monkeypatch.delenv("ATRIA_API_KEY", raising=False)
    html = app["c"].get("/cliente/acme/referentes/traer", headers={"X-Requested-With": "fetch"}).data.decode()
    assert 'name="pais"' in html
    assert 'data-solo-fuente="apify"' in html


def test_traer_form_solo_atria_no_muestra_pais(app, monkeypatch):
    monkeypatch.setenv("ATRIA_API_KEY", "atria-sk_test")
    monkeypatch.delenv("APIFY_TOKEN", raising=False)
    html = app["c"].get("/cliente/acme/referentes/traer", headers={"X-Requested-With": "fetch"}).data.decode()
    assert 'name="fuente" value="atria"' in html or 'name="fuente"' not in html  # única fuente: radio o hidden, según el conteo
    assert 'name="min_dias"' in html


def test_traer_post_apify_encola_barrer(app, monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "tok_test")
    llamadas = []
    from tareas import referentes as tareas_referentes
    monkeypatch.setattr(tareas_referentes, "encolar_barrer", lambda *a, **kw: llamadas.append((a, kw)))
    monkeypatch.setattr("referentes.fuentes.apify_adlibrary.estimar", lambda consulta, tope: {"usd_fuente": 1.16, "resultados": tope, "detalle": "x"})
    r = app["c"].post("/cliente/acme/referentes/traer", data={
        "fuente": "apify", "modo": "palabra", "palabra": "sandalias", "idioma": "es", "pais": "CO", "tope": "200",
    })
    assert r.status_code == 302
    assert len(llamadas) == 1
    args, kw = llamadas[0]
    assert args[0] == "acme" and args[1] == "apify"
    assert args[2]["pais"] == "CO"


def test_barridos_lista_los_del_cliente(app):
    from referentes import datos
    # No se afirma sobre str(bid): la fila no incrusta el id salvo en las
    # acciones condicionales (clasificar pendientes / reintentar imágenes),
    # que no aplican a un barrido recién creado -- afirmar contra str(bid)
    # dependía de que la marca de tiempo (no determinista) trajera el dígito
    # por casualidad, y fallaba en cualquier segundo sin un "1".
    datos.crear_barrido("acme", "atria", {"modo": "palabra", "palabra": "protein", "idioma": "en"}, 50)
    r = app["c"].get("/cliente/acme/referentes/barridos", headers={"X-Requested-With": "fetch"})
    assert r.status_code == 200
    assert b"protein" in r.data


def test_barridos_no_lista_los_de_otro_cliente(app):
    from referentes import datos
    ajeno = datos.crear_barrido("otro", "atria", {"modo": "palabra", "palabra": "x", "idioma": "en"}, 50)
    r = app["c"].get("/cliente/acme/referentes/barridos", headers={"X-Requested-With": "fetch"})
    assert r.status_code == 200
    assert str(ajeno).encode() not in r.data


def test_barridos_muestra_progreso_y_oculta_botones_si_hay_trabajo(app, monkeypatch):
    from referentes import datos
    from tareas import referentes as tareas_referentes
    bid = datos.crear_barrido("acme", "atria", {"modo": "palabra", "palabra": "x", "idioma": "en"}, 50)
    datos.actualizar_barrido(bid, pendientes=3)
    monkeypatch.setattr(tareas_referentes, "trabajo_barrer", lambda b: f"referentes:barrer:{b}")
    html = app["c"].get("/cliente/acme/referentes/barridos", headers={"X-Requested-With": "fetch"}).data.decode()
    # Important 3: ya no hay <script>iniciarPolling(...)> inline (nunca corría,
    # el fragmento siempre llega por fetch + innerHTML) -- data-poll-job es lo
    # que _tab_referentes.html escanea desde afuera para arrancarlo.
    assert "iniciarPolling" not in html
    assert f'data-poll-job="referentes:barrer:{bid}"' in html
    assert "Clasificar pendientes" not in html
    assert "Reintentar imágenes" not in html


def test_barridos_muestra_botones_si_no_hay_trabajo_en_curso(app, monkeypatch):
    from referentes import datos
    from tareas import referentes as tareas_referentes
    bid = datos.crear_barrido("acme", "atria", {"modo": "palabra", "palabra": "x", "idioma": "en"}, 50)
    datos.actualizar_barrido(bid, pendientes=3)
    rid, _ = datos.guardar_referente({"anuncio_id": "img-err-1", "fuente": "atria", "imagen_origen": "https://x/1.jpg",
                                      "marca": "M", "titular": "T", "cuerpo": "", "idioma": "en"},
                                     cliente="acme", barrido_id=bid)
    datos.marcar_imagen(rid, "error")
    monkeypatch.setattr(tareas_referentes, "trabajo_barrer", lambda b: None)
    html = app["c"].get("/cliente/acme/referentes/barridos", headers={"X-Requested-With": "fetch"}).data.decode()
    assert "data-poll-job" not in html
    assert "Clasificar pendientes" in html
    assert "Reintentar imágenes" in html


def test_barridos_muestra_precio_de_clasificar_pendientes(app, monkeypatch):
    """Critical 1 (segunda parte): «Clasificar pendientes» re-factura (spec
    §11) -- antes no mostraba nada. El precio sale de gastos.estimar,
    calculado en la ruta y pasado a la plantilla."""
    from referentes import datos
    from tareas import referentes as tareas_referentes
    import gastos
    bid = datos.crear_barrido("acme", "atria", {"modo": "palabra", "palabra": "x", "idioma": "en"}, 50)
    datos.actualizar_barrido(bid, pendientes=3)
    monkeypatch.setattr(tareas_referentes, "trabajo_barrer", lambda b: None)
    html = app["c"].get("/cliente/acme/referentes/barridos", headers={"X-Requested-With": "fetch"}).data.decode()
    precio = gastos.estimar("clasificacion", n=3)["texto"]
    assert precio in html


def test_barridos_sin_pendientes_no_ofrece_clasificar(app, monkeypatch):
    from referentes import datos
    from tareas import referentes as tareas_referentes
    datos.crear_barrido("acme", "atria", {"modo": "palabra", "palabra": "x", "idioma": "en"}, 50)  # pendientes=0
    monkeypatch.setattr(tareas_referentes, "trabajo_barrer", lambda b: None)
    html = app["c"].get("/cliente/acme/referentes/barridos", headers={"X-Requested-With": "fetch"}).data.decode()
    assert "Clasificar pendientes" not in html
    # Important 6.3: sin ninguna imagen en error, «Reintentar imágenes» tampoco
    # se ofrece -- antes se mostraba siempre que no hubiera trabajo en curso,
    # y un clic sin nada que reintentar igual reseteaba el barrido.
    assert "Reintentar imágenes" not in html


def test_barridos_con_imagenes_en_error_ofrece_reintentar(app, monkeypatch):
    from referentes import datos
    from tareas import referentes as tareas_referentes
    bid = datos.crear_barrido("acme", "atria", {"modo": "palabra", "palabra": "x", "idioma": "en"}, 50)
    rid, _ = datos.guardar_referente({"anuncio_id": "img-err-2", "fuente": "atria", "imagen_origen": "https://x/2.jpg",
                                      "marca": "M", "titular": "T", "cuerpo": "", "idioma": "en"},
                                     cliente="acme", barrido_id=bid)
    datos.marcar_imagen(rid, "error")
    monkeypatch.setattr(tareas_referentes, "trabajo_barrer", lambda b: None)
    html = app["c"].get("/cliente/acme/referentes/barridos", headers={"X-Requested-With": "fetch"}).data.decode()
    assert "Reintentar imágenes" in html


def test_barridos_estado_error_sin_imagenes_no_ofrece_reintentar(app, monkeypatch):
    """Important 6.3: un barrido que falló ANTES de traer ninguna fila (p. ej.
    error de la fuente en la fase "trayendo") no tiene ninguna imagen que
    reintentar -- «Reintentar imágenes» no debe ofrecerse ahí tampoco, aunque
    su estado sea "error", porque el único trabajo de ese botón es reintentar
    descargas de imagen, no reintentar el barrido entero."""
    from referentes import datos
    from tareas import referentes as tareas_referentes
    bid = datos.crear_barrido("acme", "atria", {"modo": "palabra", "palabra": "x", "idioma": "en"}, 50)
    datos.actualizar_barrido(bid, estado="error", aviso="Atria no aceptó la llave (ATRIA_API_KEY).")
    monkeypatch.setattr(tareas_referentes, "trabajo_barrer", lambda b: None)
    html = app["c"].get("/cliente/acme/referentes/barridos", headers={"X-Requested-With": "fetch"}).data.decode()
    assert "Reintentar imágenes" not in html


def test_clasificar_pendientes_encola(app, monkeypatch):
    from referentes import datos
    from tareas import referentes as tareas_referentes
    bid = datos.crear_barrido("acme", "atria", {"modo": "palabra", "palabra": "x", "idioma": "en"}, 50)
    llamadas = []
    monkeypatch.setattr(tareas_referentes, "encolar_clasificar_pendientes", lambda c, b: llamadas.append((c, b)) or True)
    r = app["c"].post(f"/cliente/acme/referentes/{bid}/clasificar_pendientes", follow_redirects=False)
    assert r.status_code == 302
    assert llamadas == [("acme", bid)]


def test_reintentar_imagenes_encola(app, monkeypatch):
    from referentes import datos
    from tareas import referentes as tareas_referentes
    bid = datos.crear_barrido("acme", "atria", {"modo": "palabra", "palabra": "x", "idioma": "en"}, 50)
    llamadas = []
    monkeypatch.setattr(tareas_referentes, "encolar_reintentar_imagenes", lambda c, b: llamadas.append((c, b)) or True)
    r = app["c"].post(f"/cliente/acme/referentes/{bid}/reintentar_imagenes", follow_redirects=False)
    assert r.status_code == 302
    assert llamadas == [("acme", bid)]


def test_clasificar_pendientes_barrido_inexistente_404(app):
    assert app["c"].post("/cliente/acme/referentes/999999/clasificar_pendientes").status_code == 404


def test_clasificar_pendientes_barrido_ajeno_404(app):
    from referentes import datos
    bid = datos.crear_barrido("otro", "atria", {"modo": "palabra", "palabra": "x", "idioma": "en"}, 50)
    assert app["c"].post(f"/cliente/acme/referentes/{bid}/clasificar_pendientes").status_code == 404


def test_reintentar_imagenes_barrido_inexistente_404(app):
    assert app["c"].post("/cliente/acme/referentes/999999/reintentar_imagenes").status_code == 404


def test_reintentar_imagenes_barrido_ajeno_404(app):
    from referentes import datos
    bid = datos.crear_barrido("otro", "atria", {"modo": "palabra", "palabra": "x", "idioma": "en"}, 50)
    assert app["c"].post(f"/cliente/acme/referentes/{bid}/reintentar_imagenes").status_code == 404


def test_pestana_muestra_botones_traer_y_barridos_con_o_sin_referentes(app):
    c = app["c"]
    html_vacio = c.get("/cliente/acme").data.decode()
    assert "Todavía no hay referentes" in html_vacio
    assert "Traer referentes" in html_vacio and "Mis barridos" in html_vacio
    _sembrar()
    html_lleno = c.get("/cliente/acme").data.decode()
    assert "Traer referentes" in html_lleno and "Mis barridos" in html_lleno


# «Mis barridos» en texto normal: nada de `en_cola`, fechas ISO ni `12/50`.

def _barridos_html(app):
    return app["c"].get("/cliente/acme/referentes/barridos", headers={"X-Requested-With": "fetch"}).data.decode()


def test_barridos_muestran_fecha_legible(app, monkeypatch):
    import db
    from referentes import datos
    monkeypatch.setattr(db, "ahora", lambda: "2026-09-25T15:04:09")
    datos.crear_barrido("acme", "atria", {"modo": "palabra", "palabra": "protein", "idioma": "en"}, 50)
    html = _barridos_html(app)
    assert "25 sep · 15:04" in html
    assert "2026-09-25T15:04" not in html


def test_barridos_muestran_estado_busqueda_cantidades_y_costo_legibles(app):
    from referentes import datos
    bid = datos.crear_barrido("acme", "atria", {"modo": "palabra", "palabra": "crema antiarrugas", "idioma": "es",
                                                "formato": "video"}, 50)
    datos.actualizar_barrido(bid, estado="parcial", traidos=12, clasificados=10, pendientes=2, usd_real=0.06,
                             aviso="Se detuvo de traer más anuncios: se acabó el cupo mensual de Atria.")
    html = _barridos_html(app)
    assert "Incompleto" in html and ">parcial<" not in html
    assert "«crema antiarrugas»" in html
    assert "Atria · Video" in html
    assert "12 de 50" in html
    assert "2 sin clasificar" in html
    assert "US$ 0,06" in html
    assert "se acabó el cupo mensual de Atria" in html


def test_barridos_de_marca_enlazan_la_pagina_en_meta(app):
    from referentes import datos
    datos.crear_barrido("acme", "apify", {"modo": "marca", "pagina_id": "110811200743559", "pais": "CO"}, 100)
    html = _barridos_html(app)
    assert "En cola" in html and ">en_cola<" not in html
    assert "view_all_page_id=110811200743559" in html
    assert "Apify · Imagen · CO" in html


def test_barridos_sin_gasto_muestran_raya(app):
    from referentes import datos
    datos.crear_barrido("acme", "atria", {"modo": "palabra", "palabra": "x", "idioma": "es"}, 10)
    html = _barridos_html(app)
    assert "US$ 0,00" not in html
    assert "—" in html
