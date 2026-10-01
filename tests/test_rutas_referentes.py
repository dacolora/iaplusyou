"""Rutas del Blueprint referentes: grid y ficha como fragmentos; visibilidad por cliente."""
import pytest


@pytest.fixture(autouse=True)
def _con_copycoders(monkeypatch):
    """Estos casos siembran la biblioteca global de copycoders y la leen desde
    un proyecto: el proyecto la trajo (desde 2026-09-28 nace apagada; el caso
    apagado vive en test_referentes_copycoders_proyecto.py)."""
    import proyectos
    monkeypatch.setattr(proyectos, "referentes_copycoders", lambda cliente: True)


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
    # Barridos por palabra: la traducción al inglés llama a Claude. En los
    # tests nunca sale a la red: devuelve la palabra tal cual.
    from referentes import traducir
    monkeypatch.setattr(traducir, "_llamar", lambda texto: (texto.rsplit("Keyword: ", 1)[-1].strip(), 0, 0))
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
    assert "Generar 2 videos" in html_video and "Cámara fija" in html_video
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
    assert body["titular"] == "SE ACABA HOY" and body["prompt"] == "Con Image 1 e Image 2..." and "angulo" in body
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


def test_recrear_generar_guarda_el_angulo_validado(app, monkeypatch):
    import json
    import creative_flow
    import flowplus_lanzar
    ids = _sembrar()
    monkeypatch.setattr("referentes.recrear.r2_uploader.upload_image", lambda local, clave: f"https://r2/{clave}")
    lanzados = []
    monkeypatch.setattr(flowplus_lanzar, "lanzar", lambda cliente, cf_id, entry, **kw: lanzados.append(cf_id) or True)
    angulo = {"audiencia": "a", "consciencia": "consciente_del_producto", "sofisticacion": 2, "deseo": "d",
              "promesa": "p", "mecanismo": None, "pruebas": [], "lead": "promesa", "gancho": "g", "faltantes": []}
    base = {"producto_id": "espejo_led", "formato": "1:1", "titular": "T", "prompt": "P", "tipo": "imagen"}
    app["c"].post(f"/cliente/acme/referentes/{ids[0]}/recrear/generar", data=dict(base, angulo=json.dumps(angulo)))
    entry = creative_flow.cargar("acme")[lanzados[0]]
    assert entry["angulo"]["promesa"] == "p" and entry["angulo"]["origen"] == "recrear"
    app["c"].post(f"/cliente/acme/referentes/{ids[0]}/recrear/generar", data=dict(base, angulo="no es json"))
    assert "angulo" not in creative_flow.cargar("acme")[lanzados[1]]


def test_recrear_generar_no_pierde_los_errores_del_angulo_al_revalidarlo(app, monkeypatch):
    """Fix 2: el ángulo que devuelve el navegador ya trae sus «error: …»
    (después de 5 faltantes de Claude); al revalidarlo en la ruta van
    primero y ninguno se cae por el tope."""
    import json
    import creative_flow
    import flowplus_lanzar
    ids = _sembrar()
    monkeypatch.setattr("referentes.recrear.r2_uploader.upload_image", lambda local, clave: f"https://r2/{clave}")
    lanzados = []
    monkeypatch.setattr(flowplus_lanzar, "lanzar", lambda cliente, cf_id, entry, **kw: lanzados.append(cf_id) or True)
    errores = ["error: gancho_largo", "error: cifra_no_verificada:47 %", "error: mecanismo_obligatorio"]
    angulo = {"audiencia": "a", "consciencia": "consciente_del_producto", "sofisticacion": 2, "deseo": "d",
              "promesa": "p", "mecanismo": None, "pruebas": [], "lead": "promesa", "gancho": "g",
              "faltantes": [f"falta {n}" for n in range(5)] + errores}
    base = {"producto_id": "espejo_led", "formato": "1:1", "titular": "T", "prompt": "P", "tipo": "imagen"}
    app["c"].post(f"/cliente/acme/referentes/{ids[0]}/recrear/generar", data=dict(base, angulo=json.dumps(angulo)))
    assert creative_flow.cargar("acme")[lanzados[0]]["angulo"]["faltantes"][:3] == errores


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


def _script_modal_referentes(html):
    """El <script> de _tab_referentes.html que maneja el diálogo y el precio en
    vivo de «Traer referentes» (vive fuera del condicional de biblioteca vacía)."""
    ini = html.index("var modal = document.getElementById('ref-modal');")
    return html[ini:html.index("</script>", ini)]


def test_traer_form_marca_lo_que_refresca_el_precio(app, monkeypatch):
    """Incidente 2026-09-27: el refresco de precio solo reemplaza lo que depende
    del servidor, así que esas partes tienen que poder encontrarse por id."""
    monkeypatch.setenv("ATRIA_API_KEY", "atria-sk_test")
    html = app["c"].get("/cliente/acme/referentes/traer", headers={"X-Requested-With": "fetch"}).data.decode()
    for id_ in ("traer-precio", "traer-aviso", "traer-enviar"):
        assert f'id="{id_}"' in html


def test_refresco_de_precio_no_reemplaza_el_formulario(app):
    """Incidente 2026-09-27: cada pausa al escribir pedía el precio y metía el
    fragmento ENTERO con `cuerpo.innerHTML = html`. Lo tecleado mientras llegaba
    la respuesta se perdía («crema antiarrugas» quedaba «cremaarrugas»), el
    scroll del formulario volvía arriba y los campos nuevos nacían sin la marca
    `data-sucio` de base.html -- así un trabajo que terminaba en otra pestaña
    recargaba la página y cerraba el modal. Ahora solo se tocan el precio, el
    aviso de la fuente y el estado del botón, y una respuesta vieja se ignora."""
    js = _script_modal_referentes(app["c"].get("/cliente/acme").data.decode())
    precio = js[js.index("function refrescarPrecioTraer"):js.index("cuerpo.addEventListener('input'")]
    assert "innerHTML = html" not in precio
    for id_ in ("traer-precio", "traer-aviso", "traer-enviar"):
        assert id_ in precio
    assert "pedidoPrecioTraer" in precio                      # descarta respuestas que llegan tarde


def test_enter_en_un_campo_no_lanza_el_barrido(app):
    """Incidente 2026-09-27: Enter en «Palabra clave» hacía el envío implícito
    del navegador -> POST traer_post -> barrido encolado (gasta) y la página se
    recargaba, cerrando el modal. Solo el botón «Traer y clasificar» lanza."""
    js = _script_modal_referentes(app["c"].get("/cliente/acme").data.decode())
    enter = js[js.index("addEventListener('keydown'"):]
    assert "'Enter'" in enter[:400] and "preventDefault()" in enter[:600]


def test_soltar_una_seleccion_fuera_no_cierra_el_dialogo(app):
    """Incidente 2026-09-27: seleccionar texto arrastrando y soltar fuera del
    diálogo da un 'click' con target = el <dialog> y lo cerraba. Solo se cierra
    si el clic también empezó en el fondo."""
    js = _script_modal_referentes(app["c"].get("/cliente/acme").data.decode())
    assert "modal.addEventListener('mousedown'" in js


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


def _gastos_de(cliente):
    import sqlalchemy as sa
    import db
    with db.conectar() as con:
        return [dict(f._mapping) for f in con.execute(sa.select(db.gasto).where(db.gasto.c.cliente == cliente))]


def test_traer_post_traduce_la_palabra_y_busca_en_ingles(app, monkeypatch):
    """2026-09-27: los barridos por palabra van SIEMPRE en inglés (pedido del
    usuario tras «DOLOR DE PIES» en inglés = pasteles). Se traduce lo escrito,
    se guarda la original, se fuerza idioma en y se registra el gasto."""
    from referentes import traducir
    from tareas import referentes as tareas_referentes
    monkeypatch.setenv("ATRIA_API_KEY", "atria-sk_test")
    monkeypatch.setattr(traducir, "_llamar", lambda texto: ('"foot pain"\n', 40, 6))
    llamadas = []
    monkeypatch.setattr(tareas_referentes, "encolar_barrer", lambda *a, **kw: llamadas.append(a) or 1)
    app["c"].post("/cliente/acme/referentes/traer", data={"fuente": "atria", "modo": "palabra", "palabra": "dolor de pies",
                                                         "idioma": "es", "tope": "20"})
    consulta = llamadas[0][2]
    assert (consulta["palabra"], consulta["palabra_original"], consulta["idioma"]) == ("foot pain", "dolor de pies", "en")
    (g,) = _gastos_de("acme")
    assert g["tipo"] == "otro" and g["usd"] > 0 and "dolor de pies" in g["detalle"] and "foot pain" in g["detalle"]


def test_traer_post_si_no_se_puede_traducir_no_lanza_nada(app, monkeypatch):
    from referentes import traducir
    from tareas import referentes as tareas_referentes
    monkeypatch.setenv("ATRIA_API_KEY", "atria-sk_test")
    monkeypatch.setattr(traducir, "_llamar", lambda texto: (_ for _ in ()).throw(RuntimeError("Anthropic caído")))
    llamadas = []
    monkeypatch.setattr(tareas_referentes, "encolar_barrer", lambda *a, **kw: llamadas.append(a) or 1)
    c = app["c"]
    c.post("/cliente/acme/referentes/traer", data={"fuente": "atria", "modo": "palabra", "palabra": "dolor de pies", "tope": "20"})
    assert llamadas == []
    with c.session_transaction() as s:
        assert any("traducir" in m for _, m in s.get("_flashes", []))


def test_admin_barrido_global_tambien_en_ingles(app, monkeypatch):
    from referentes import traducir
    from tareas import referentes as tr
    monkeypatch.setenv("ATRIA_API_KEY", "atria-sk_test")
    monkeypatch.setattr(traducir, "_llamar", lambda texto: ("shoes", 30, 2))
    llamadas = []
    monkeypatch.setattr(tr, "encolar_barrer", lambda *a, **kw: llamadas.append(a) or True)
    app["c"].post("/admin/referentes/traer", data={"fuente": "atria", "modo": "palabra", "palabra": "zapatos", "idioma": "es",
                                                  "tope": "50"}, headers={"Sec-Fetch-Site": "same-origin"})
    assert (llamadas[0][2]["palabra"], llamadas[0][2]["idioma"]) == ("shoes", "en")
    assert [g["tipo"] for g in _gastos_de("_creatv")] == ["otro"]


def test_mis_barridos_muestra_lo_escrito_y_lo_buscado(app):
    from referentes import datos
    datos.crear_barrido("acme", "atria", {"modo": "palabra", "palabra": "foot pain", "palabra_original": "dolor de pies",
                                          "idioma": "en"}, 20)
    html = app["c"].get("/cliente/acme/referentes/barridos").get_data(as_text=True)
    assert "«dolor de pies» → «foot pain»" in html


def test_formularios_de_barrido_ya_no_piden_idioma(app, monkeypatch):
    monkeypatch.setenv("ATRIA_API_KEY", "atria-sk_test")
    html = app["c"].get("/cliente/acme/referentes/traer").get_data(as_text=True)
    assert 'name="idioma"' not in html and "inglés" in html
    html = app["c"].get("/admin/referentes").get_data(as_text=True)
    assert 'name="idioma"' not in html


def test_al_ingles_limpia_comillas_y_rechaza_vacio(monkeypatch):
    from referentes import traducir
    monkeypatch.setattr(traducir, "_llamar", lambda texto: ("«foot pain relief»\nExplanation…", 1, 1))
    assert traducir.al_ingles("alivio del dolor de pies")[0] == "foot pain relief"
    monkeypatch.setattr(traducir, "_llamar", lambda texto: ("  ", 1, 1))
    with pytest.raises(traducir.TraduccionInvalida):
        traducir.al_ingles("x")


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
    # La barra se veía como un punto (celda sin ancho) y su texto («61/100») iba
    # DENTRO de la barra (overflow hidden): ahora tiene ancho mínimo y el texto
    # va debajo, como hermano (iniciarPolling lo busca ahí).
    assert ('<div class="barrido-progreso"><div class="barra-progreso" id="trabajo-referentes:barrer:%d" '
            'data-poll-job="referentes:barrer:%d"><div class="barra-progreso-fill"></div></div>'
            '<span class="progreso-texto"></span></div>') % (bid, bid) in html


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
    assert "25 sept · 15:04" in html
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


def test_admin_referentes_muestra_totales_y_cuota_atria(app, monkeypatch):
    from referentes.fuentes import atria as atria_mod
    monkeypatch.setattr(atria_mod, "llamadas_este_mes", lambda: 37)
    monkeypatch.setattr(atria_mod, "limite_mensual", lambda: 1200)
    html = app["c"].get("/admin/referentes").data.decode()
    assert "37" in html and "1200" in html


def test_admin_referentes_lista_barridos_de_otras_fuentes(app):
    from referentes import datos
    bid = datos.crear_barrido(None, "atria", {"modo": "palabra", "palabra": "sandalias"}, 50)
    datos.actualizar_barrido(bid, estado="listo", traidos=12, clasificados=10, usd_real=0.32)
    html = app["c"].get("/admin/referentes").data.decode()
    assert "sandalias" in html and "atria" in html


def test_admin_referentes_familia_actualizar(app):
    from referentes import datos
    fid = datos.familia_asegurar("Price Slash Hero", "vieja descripción")
    c = app["c"]
    r = c.post(f"/admin/referentes/familias/{fid}", data={"descripcion": "Escalera de precios tachados"},
              headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/admin/referentes")
    familia = [f for f in datos.familias() if f["id"] == fid][0]
    assert familia["descripcion"] == "Escalera de precios tachados"


def test_admin_referentes_familia_actualizar_inexistente(app):
    c = app["c"]
    r = c.post("/admin/referentes/familias/999999", data={"descripcion": "x"}, headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 302   # no revienta con un id que no existe


def test_admin_referentes_familia_actualizar_solo_admin(app):
    from referentes import datos
    fid = datos.familia_asegurar("Comic Strip", "original")
    c = app["dashboard"].app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "otro"; s["rol"] = "cliente"; s["cliente"] = "otro"
    r = c.post(f"/admin/referentes/familias/{fid}", data={"descripcion": "hackeado"}, headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 302
    familia = [f for f in datos.familias() if f["id"] == fid][0]
    assert familia["descripcion"] == "original"


# --- reparo bloque 6: un barrido global «parcial» no tenía forma de
# reintentarse desde /admin/referentes (las rutas por-cliente que ya hacían
# esto -- referentes.rutas.clasificar_pendientes/reintentar_imagenes --
# siempre 404 para un barrido con cliente=None, spec Important del review
# final). Estas rutas son el equivalente admin: mismo comportamiento, pero
# gateadas por "es global" en vez de "es de este proyecto".

def test_admin_referentes_clasificar_encola(app, monkeypatch):
    from referentes import datos
    from tareas import referentes as tareas_referentes
    bid = datos.crear_barrido(None, "atria", {"modo": "palabra", "palabra": "x", "idioma": "en"}, 50)
    datos.actualizar_barrido(bid, estado="parcial", pendientes=3,
                             aviso="3 referentes no se pudieron clasificar; «Clasificar pendientes» los vuelve a pedir.")
    llamadas = []
    monkeypatch.setattr(tareas_referentes, "encolar_clasificar_pendientes", lambda c, b: llamadas.append((c, b)) or True)
    r = app["c"].post(f"/admin/referentes/barridos/{bid}/clasificar", headers={"Sec-Fetch-Site": "same-origin"},
                      follow_redirects=False)
    assert r.status_code == 302 and r.headers["Location"].endswith("/admin/referentes")
    assert llamadas == [(None, bid)]


def test_admin_referentes_reintentar_imagenes_encola(app, monkeypatch):
    from referentes import datos
    from tareas import referentes as tareas_referentes
    bid = datos.crear_barrido(None, "atria", {"modo": "palabra", "palabra": "x", "idioma": "en"}, 50)
    datos.actualizar_barrido(bid, estado="parcial",
                             aviso="1 imagen no se pudo bajar; «Reintentar imágenes» las vuelve a pedir.")
    llamadas = []
    monkeypatch.setattr(tareas_referentes, "encolar_reintentar_imagenes", lambda c, b: llamadas.append((c, b)) or True)
    r = app["c"].post(f"/admin/referentes/barridos/{bid}/reintentar-imagenes", headers={"Sec-Fetch-Site": "same-origin"},
                      follow_redirects=False)
    assert r.status_code == 302 and r.headers["Location"].endswith("/admin/referentes")
    assert llamadas == [(None, bid)]


def test_admin_referentes_clasificar_barrido_inexistente_404(app):
    r = app["c"].post("/admin/referentes/barridos/999999/clasificar", headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 404


def test_admin_referentes_reintentar_imagenes_barrido_inexistente_404(app):
    r = app["c"].post("/admin/referentes/barridos/999999/reintentar-imagenes", headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 404


def test_admin_referentes_clasificar_barrido_de_cliente_404(app):
    """Nunca una puerta trasera: un barrido con dueño real (cliente="acme")
    no es global y estas rutas admin deben rechazarlo igual que
    `referentes.rutas.clasificar_pendientes` rechaza uno ajeno."""
    from referentes import datos
    bid = datos.crear_barrido("acme", "atria", {"modo": "palabra", "palabra": "x", "idioma": "en"}, 50)
    r = app["c"].post(f"/admin/referentes/barridos/{bid}/clasificar", headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 404


def test_admin_referentes_reintentar_imagenes_barrido_de_cliente_404(app):
    from referentes import datos
    bid = datos.crear_barrido("acme", "atria", {"modo": "palabra", "palabra": "x", "idioma": "en"}, 50)
    r = app["c"].post(f"/admin/referentes/barridos/{bid}/reintentar-imagenes", headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 404


def test_admin_referentes_clasificar_solo_admin(app, monkeypatch):
    from referentes import datos
    from tareas import referentes as tareas_referentes
    bid = datos.crear_barrido(None, "atria", {"modo": "palabra", "palabra": "x", "idioma": "en"}, 50)
    llamadas = []
    monkeypatch.setattr(tareas_referentes, "encolar_clasificar_pendientes", lambda c, b: llamadas.append((c, b)) or True)
    c = app["dashboard"].app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "otro"; s["rol"] = "cliente"; s["cliente"] = "otro"
    r = c.post(f"/admin/referentes/barridos/{bid}/clasificar", headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 302
    assert llamadas == []


def test_admin_referentes_reintentar_imagenes_solo_admin(app, monkeypatch):
    from referentes import datos
    from tareas import referentes as tareas_referentes
    bid = datos.crear_barrido(None, "atria", {"modo": "palabra", "palabra": "x", "idioma": "en"}, 50)
    llamadas = []
    monkeypatch.setattr(tareas_referentes, "encolar_reintentar_imagenes", lambda c, b: llamadas.append((c, b)) or True)
    c = app["dashboard"].app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "otro"; s["rol"] = "cliente"; s["cliente"] = "otro"
    r = c.post(f"/admin/referentes/barridos/{bid}/reintentar-imagenes", headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 302
    assert llamadas == []


def test_admin_referentes_ofrece_reintentos_en_barrido_global_parcial(app, monkeypatch):
    """La página en sí ofrece los botones (el hueco original: la tabla no
    tenía ninguno) cuando el barrido global tiene algo que reintentar."""
    from referentes import datos
    from tareas import referentes as tareas_referentes
    bid = datos.crear_barrido(None, "atria", {"modo": "palabra", "palabra": "sandalias", "idioma": "es"}, 50)
    rid, _ = datos.guardar_referente({"anuncio_id": "img-err-glob", "fuente": "atria", "imagen_origen": "https://x/9.jpg",
                                      "marca": "M", "titular": "T", "cuerpo": "", "idioma": "en"},
                                     cliente=None, barrido_id=bid)
    datos.marcar_imagen(rid, "error")
    datos.actualizar_barrido(bid, estado="parcial", pendientes=2,
                             aviso="2 referentes no se pudieron clasificar; «Clasificar pendientes» los vuelve a pedir. "
                                   "1 imagen no se pudo bajar; «Reintentar imágenes» las vuelve a pedir.")
    monkeypatch.setattr(tareas_referentes, "trabajo_barrer", lambda b: None)
    html = app["c"].get("/admin/referentes").data.decode()
    assert f"/admin/referentes/barridos/{bid}/clasificar" in html and "Clasificar pendientes" in html
    assert f"/admin/referentes/barridos/{bid}/reintentar-imagenes" in html and "Reintentar imágenes" in html


def test_admin_referentes_muestra_progreso_y_oculta_botones_si_hay_trabajo(app, monkeypatch):
    from referentes import datos
    from tareas import referentes as tareas_referentes
    bid = datos.crear_barrido(None, "atria", {"modo": "palabra", "palabra": "x", "idioma": "en"}, 50)
    datos.actualizar_barrido(bid, pendientes=3)
    monkeypatch.setattr(tareas_referentes, "trabajo_barrer", lambda b: f"referentes:barrer:{b}")
    html = app["c"].get("/admin/referentes").data.decode()
    assert f"iniciarPolling(\"referentes:barrer:{bid}\"" in html
    assert "Clasificar pendientes" not in html
    assert "Reintentar imágenes" not in html


def test_admin_referentes_sin_pendientes_ni_errores_no_ofrece_botones(app, monkeypatch):
    from referentes import datos
    from tareas import referentes as tareas_referentes
    datos.crear_barrido(None, "atria", {"modo": "palabra", "palabra": "x", "idioma": "en"}, 50)  # pendientes=0, sin errores
    monkeypatch.setattr(tareas_referentes, "trabajo_barrer", lambda b: None)
    html = app["c"].get("/admin/referentes").data.decode()
    assert "Clasificar pendientes" not in html
    assert "Reintentar imágenes" not in html


def test_recrear_adaptar_le_pasa_la_sofisticacion_del_catalogo(app, monkeypatch):
    """Doctrina, bloque 2: la ruta lee la sofisticación de la fila `producto`."""
    import tiendas
    from referentes import recrear
    ids = _sembrar()
    fila = tiendas.asegurar_manual("acme", "espejo_led", "Espejo LED")
    tiendas.anotar_extra("acme", fila, sofisticacion=5)
    visto = {}

    def falso(texto, max_tokens):
        visto["texto"] = texto
        return '{"titular": "SE ACABA HOY", "prompt": "Con Image 1 e Image 2..."}', 150, 40
    monkeypatch.setattr(recrear, "_llamar", falso)
    app["c"].post(f"/cliente/acme/referentes/{ids[0]}/recrear/adaptar", json={"producto_id": "espejo_led"})
    assert "Sofisticación del mercado (fija, no la cambies): 5" in visto["texto"]


def test_recrear_adaptar_descarta_una_sofisticacion_invalida_del_catalogo(app, monkeypatch):
    """Bloque 2, revisión final #6: sofisticación fuera de 1-5 (dato corrupto
    en `producto.extra`) se descarta en la ruta antes de fijarla en el
    ángulo, igual que ya hacen ideas y el guion
    (`sof if sof in doctrina.SOFISTICACIONES else None`)."""
    import tiendas
    from referentes import recrear
    ids = _sembrar()
    fila = tiendas.asegurar_manual("acme", "espejo_led", "Espejo LED")
    tiendas.anotar_extra("acme", fila, sofisticacion=9)
    visto = {}

    def falso_adaptar(referente, familia, producto, titular_actual, guia="", idioma="es", **kw):
        visto["sofisticacion"] = producto.get("sofisticacion")
        return {"titular": "T", "prompt": "P", "angulo": {}}, 10, 5
    monkeypatch.setattr(recrear, "adaptar", falso_adaptar)
    r = app["c"].post(f"/cliente/acme/referentes/{ids[0]}/recrear/adaptar", json={"producto_id": "espejo_led"})
    assert r.status_code == 200
    assert visto["sofisticacion"] is None


def test_filtros_plegables_en_el_celular(app):
    """Revisión de celular 2026-09-28: las pastillas de etapa y consciencia más los
    cuatro selectores y la búsqueda ocupaban toda la primera pantalla antes del
    primer anuncio. En el celular van detrás de «Filtros» (con cuántos hay puestos);
    en escritorio el envoltorio es `display: contents` y todo queda como antes."""
    _sembrar()
    html = app["c"].get("/cliente/acme").data.decode()
    assert 'id="ref-filtros-boton"' in html and 'aria-controls="ref-filtros"' in html
    assert 'aria-expanded="false"' in html
    i, j = html.index('id="ref-filtros"'), html.index('id="ref-grid"')
    bloque = html[i:j]
    assert 'data-filtro="etapa"' in bloque and 'data-filtro="consciencia"' in bloque
    assert 'data-filtro="marca"' in bloque and 'data-filtro="q"' in bloque
    assert "function contarFiltros()" in html
    css = open("static/style.css", encoding="utf-8").read()
    assert ".ref-filtros { display: contents; }" in css
    assert ".ref-filtros:not(.abierto) { display: none; }" in css


# ------------------------------------------------------------- TrendTrack ---

def _estimar_trendtrack(monkeypatch):
    from referentes.fuentes import trendtrack
    monkeypatch.setenv("TRENDTRACK_API_KEY", "tt_test")
    monkeypatch.setattr(trendtrack, "estimar", lambda consulta, tope: {
        "usd_fuente": 0.0, "llamadas": 6, "detalle": "hasta 300 créditos de TrendTrack"})


def test_traer_form_trendtrack_por_palabra_muestra_precio_y_oculta_lo_de_atria(app, monkeypatch):
    _estimar_trendtrack(monkeypatch)
    html = app["c"].get("/cliente/acme/referentes/traer?fuente=trendtrack&modo=palabra&palabra=foot+pain&tope=100",
                        headers={"X-Requested-With": "fetch"}).data.decode()
    assert "hasta 300 créditos de TrendTrack" in html
    assert 'value="trendtrack"' in html and 'data-no-fuente="trendtrack"' in html
    assert "solo busca por palabra clave" not in html                  # el aviso es solo para el modo marca
    assert "disabled" not in html[html.index('id="traer-enviar"'):html.index('id="traer-enviar"') + 80]


def test_traer_form_trendtrack_en_modo_marca_avisa_y_no_deja_enviar(app, monkeypatch):
    _estimar_trendtrack(monkeypatch)
    llamadas = []
    monkeypatch.setattr("referentes.fuentes.trendtrack.estimar", lambda c, t: llamadas.append(c) or {})
    html = app["c"].get("/cliente/acme/referentes/traer?fuente=trendtrack&modo=marca&pagina_id=123",
                        headers={"X-Requested-With": "fetch"}).data.decode()
    assert "solo busca por palabra clave" in html and llamadas == []   # ni siquiera estima
    boton = html[html.index('id="traer-enviar"'):]
    assert "disabled" in boton[:boton.index(">")]


def test_traer_post_trendtrack_en_modo_marca_no_lanza(app, monkeypatch):
    from tareas import referentes as tr
    _estimar_trendtrack(monkeypatch)
    llamadas = []
    monkeypatch.setattr(tr, "encolar_barrer", lambda *a, **kw: llamadas.append(a) or True)
    r = app["c"].post("/cliente/acme/referentes/traer", headers={"Sec-Fetch-Site": "same-origin"},
                      data={"fuente": "trendtrack", "modo": "marca", "pagina_id": "123", "tope": "50"}, follow_redirects=True)
    assert "no admite este tipo de búsqueda" in r.data.decode() and llamadas == []


def test_traer_post_trendtrack_por_palabra_lanza_el_barrido(app, monkeypatch):
    from tareas import referentes as tr
    _estimar_trendtrack(monkeypatch)
    llamadas = []
    monkeypatch.setattr(tr, "encolar_barrer", lambda *a, **kw: llamadas.append(a) or True)
    r = app["c"].post("/cliente/acme/referentes/traer", headers={"Sec-Fetch-Site": "same-origin"},
                      data={"fuente": "trendtrack", "modo": "palabra", "palabra": "foot pain", "tope": "50"})
    assert r.status_code == 302 and len(llamadas) == 1
    assert llamadas[0][1] == "trendtrack" and llamadas[0][2]["palabra"] and llamadas[0][3] == 50


def test_traer_post_trendtrack_sin_llave_no_lanza(app, monkeypatch):
    from tareas import referentes as tr
    monkeypatch.delenv("TRENDTRACK_API_KEY", raising=False)
    llamadas = []
    monkeypatch.setattr(tr, "encolar_barrer", lambda *a, **kw: llamadas.append(a) or True)
    r = app["c"].post("/cliente/acme/referentes/traer", headers={"Sec-Fetch-Site": "same-origin"},
                      data={"fuente": "trendtrack", "modo": "palabra", "palabra": "foot pain"}, follow_redirects=True)
    assert "no está configurada" in r.data.decode() and llamadas == []


def test_admin_trendtrack_modo_marca_no_lanza_y_el_panel_muestra_los_creditos(app, monkeypatch):
    from referentes.fuentes import trendtrack
    from tareas import referentes as tr
    _estimar_trendtrack(monkeypatch)
    llamadas = []
    monkeypatch.setattr(tr, "encolar_barrer", lambda *a, **kw: llamadas.append(a) or True)
    c = app["c"]
    r = c.post("/admin/referentes/traer", headers={"Sec-Fetch-Site": "same-origin"},
               data={"fuente": "trendtrack", "modo": "marca", "pagina_id": "123"}, follow_redirects=True)
    assert "no admite este tipo de búsqueda" in r.data.decode() and llamadas == []
    trendtrack._sumar_creditos(42)
    trendtrack._guardar_saldo({"X-Credits-Remaining": "19958"})
    html = c.get("/admin/referentes?fuente=trendtrack&modo=palabra&palabra=foot+pain").data.decode()
    assert "TrendTrack: 42 créditos gastados" in html and "le quedaban 19958 créditos" in html
    assert "Traer y clasificar ≈ US$" in html
    # sin llave, el contador no se muestra
    monkeypatch.delenv("TRENDTRACK_API_KEY")
    assert "TrendTrack: 42 créditos" not in c.get("/admin/referentes").data.decode()


# --- Recrear fiel (spec 2026-09-30-recrear-fiel) ---

LECTURA = {"version": 1, "composicion": "Two sandals side by side on a white background, seen from above",
           "producto": "heeled sandal", "unidades": 2, "personas": False, "ancho": 1080, "alto": 1080,
           "textos": [{"texto": "50% OFF", "rol": "oferta", "ubicacion": "top center"},
                      {"texto": "Inochhi", "rol": "marca", "ubicacion": "bottom right"}]}


def _con_lectura(rid, **cambios):
    from referentes import datos
    datos.guardar_lectura(rid, dict(LECTURA, **cambios))


def _sin_r2_ni_lanzar(monkeypatch):
    import flowplus_lanzar
    monkeypatch.setattr("referentes.recrear.r2_uploader.upload_image", lambda local, clave: f"https://r2/{clave}")
    lanzados = []
    monkeypatch.setattr(flowplus_lanzar, "lanzar", lambda cliente, cf_id, entry, **kw: lanzados.append(cf_id) or True)
    return lanzados


def test_recrear_leer_guarda_una_vez_y_cobra_una_vez(app, monkeypatch):
    import gastos
    from referentes import datos, lectura
    ids = _sembrar()
    llamadas = []
    monkeypatch.setattr(lectura, "leer", lambda r: llamadas.append(r["id"]) or (dict(LECTURA, modelo="m"), 900, 300))
    monkeypatch.setattr(lectura, "medir", lambda url: (1080, 1350))
    r = app["c"].post(f"/cliente/acme/referentes/{ids[0]}/recrear/leer", headers={"X-Requested-With": "fetch"})
    assert r.status_code == 200 and r.get_json() == {"ok": True, "cobrado": True}
    guardada = datos.referente("acme", ids[0])["extra"]["lectura"]
    assert guardada["composicion"] == LECTURA["composicion"] and (guardada["ancho"], guardada["alto"]) == (1080, 1350)
    gasto = gastos.historial("acme", limite=1)[0]
    assert gasto["tipo"] == "adaptar_referente" and gasto["usd"] > 0 and "lectura" in gasto["detalle"]
    r2 = app["c"].post(f"/cliente/acme/referentes/{ids[0]}/recrear/leer")
    assert r2.get_json() == {"ok": True, "cobrado": False} and llamadas == [ids[0]]
    assert len(gastos.historial("acme", limite=10)) == 1


def test_recrear_leer_falla_registra_lo_pagado_y_no_guarda(app, monkeypatch):
    import gastos
    from referentes import datos, lectura
    ids = _sembrar()

    def invalida(r):
        e = lectura.LecturaInvalida("Claude no describió la composición.")
        e.tokens_entrada, e.tokens_salida = 700, 40
        raise e
    monkeypatch.setattr(lectura, "leer", invalida)
    r = app["c"].post(f"/cliente/acme/referentes/{ids[0]}/recrear/leer")
    assert r.status_code == 502 and "composición" in r.get_json()["error"]
    assert "lectura" not in (datos.referente("acme", ids[0])["extra"] or {})
    assert gastos.historial("acme", limite=1)[0]["usd"] > 0

    def caida(r):
        raise ConnectionError("x")
    monkeypatch.setattr(lectura, "leer", caida)
    r2 = app["c"].post(f"/cliente/acme/referentes/{ids[0]}/recrear/leer")
    assert r2.status_code == 502 and "ConnectionError" in r2.get_json()["error"]
    assert app["c"].post("/cliente/acme/referentes/999999/recrear/leer").status_code == 404


def test_recrear_post_de_otro_sitio_403(app):
    ids = _sembrar()
    r = app["c"].post(f"/cliente/acme/referentes/{ids[0]}/recrear/leer", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    r2 = app["c"].post(f"/cliente/acme/referentes/{ids[0]}/recrear/generar", data={"producto_id": "espejo_led"},
                       headers={"Sec-Fetch-Site": "cross-site"})
    assert r2.status_code == 403


def test_recrear_formulario_sin_lectura_pide_leer(app):
    ids = _sembrar()
    html = app["c"].get(f"/cliente/acme/referentes/{ids[0]}/recrear").data.decode()
    assert "data-recrear-leer" in html and "Leyendo la referencia" in html
    assert f"/cliente/acme/referentes/{ids[0]}/recrear/leer" in html
    assert 'name="traer_textos"' in html and 'value="9:16" selected' in html
    assert 'name="modo" value="fiel"' in html and 'name="modo" value="libre"' in html
    assert "Generar 2 imágenes" in html and 'name="prompt_fiel"' in html


def test_recrear_formulario_con_lectura_pinta_textos_y_formato_cercano(app):
    ids = _sembrar()
    _con_lectura(ids[0])
    html = app["c"].get(f"/cliente/acme/referentes/{ids[0]}/recrear").data.decode()
    assert "data-recrear-leer" not in html
    assert 'name="texto_0"' in html and 'value="50% OFF"' in html
    assert 'name="texto_1"' in html and "Inochhi" in html          # la marca: vacía, con el original de pista
    assert 'name="texto_1" maxlength="200" value=""' in html
    assert 'value="1:1" selected' in html                            # 1080×1080 → 1:1
    assert "Image 1 muestra" in html                                 # el prompt fiel ya trae la composición


def test_recrear_formulario_sin_textos_en_la_referencia(app):
    ids = _sembrar()
    _con_lectura(ids[0], textos=[])
    html = app["c"].get(f"/cliente/acme/referentes/{ids[0]}/recrear").data.decode()
    assert "Esta referencia no tiene textos dentro de la imagen." in html and 'name="texto_0"' not in html


def test_recrear_formulario_recarga_conserva_lo_escrito(app):
    ids = _sembrar()
    _con_lectura(ids[0])
    html = app["c"].get(f"/cliente/acme/referentes/{ids[0]}/recrear?campos_vista=1&texto_0=40%25+OFF"
                        f"&modos_vista=1&modo=fiel&formato=4:5&formato_elegido=1").data.decode()
    assert 'value="40% OFF"' in html and 'value="4:5" selected' in html and 'data-elegido="1"' in html
    assert 'name="traer_textos" value="1" data-recrear-traer checked' not in html   # casilla apagada al no venir
    assert 'value="libre" data-recrear-modo checked' not in html and 'value="fiel" data-recrear-modo checked' in html


def test_recrear_generar_dos_imagenes_fiel_primero(app, monkeypatch):
    import creative_flow
    ids = _sembrar()
    _con_lectura(ids[0])
    lanzados = _sin_r2_ni_lanzar(monkeypatch)
    r = app["c"].post(f"/cliente/acme/referentes/{ids[0]}/recrear/generar",
                      data={"producto_id": "espejo_led", "formato": "1:1", "tipo": "imagen", "campos_vista": "1",
                            "traer_textos": "1", "texto_0": "40% OFF", "texto_1": "", "modos_vista": "1",
                            "modo": ["fiel", "libre"], "prompt": "viejo", "prompt_fiel": "viejo"})
    assert r.status_code == 302 and len(lanzados) == 2
    sesiones = creative_flow.cargar("acme")
    fiel, libre = sesiones[lanzados[0]], sesiones[lanzados[1]]
    assert fiel["recrear_modo"] == "fiel" and libre["recrear_modo"] == "libre"
    assert fiel["prompt_relleno"] != "viejo" and "Edita Image 1" in fiel["prompt_relleno"]
    assert "cambia «50% OFF» por «40% OFF»" in fiel["prompt_relleno"] and "quita «Inochhi»" in fiel["prompt_relleno"]
    assert "cambia «50% OFF» por «40% OFF»" in libre["prompt_relleno"] and "Sigue la ESTRUCTURA" in libre["prompt_relleno"]
    assert fiel["accion_central"] == "Recrear: 40% OFF · igual" and libre["accion_central"] == "Recrear: 40% OFF · variación"
    assert fiel["referencias_urls"] == libre["referencias_urls"] and fiel["referente_id"] == ids[0]


def test_recrear_generar_respeta_el_prompt_editado_y_un_solo_modo(app, monkeypatch):
    import creative_flow
    ids = _sembrar()
    lanzados = _sin_r2_ni_lanzar(monkeypatch)
    app["c"].post(f"/cliente/acme/referentes/{ids[0]}/recrear/generar",
                  data={"producto_id": "espejo_led", "formato": "1:1", "tipo": "imagen", "campos_vista": "1",
                        "modos_vista": "1", "modo": "fiel", "prompt_fiel": "MI PROMPT", "prompt_fiel_editado": "1"})
    assert len(lanzados) == 1
    entry = creative_flow.cargar("acme")[lanzados[0]]
    assert entry["prompt_relleno"] == "MI PROMPT" and entry["recrear_modo"] == "fiel"


def test_recrear_generar_sin_modos_o_editado_vacio_no_crea_nada(app, monkeypatch):
    import creative_flow
    ids = _sembrar()
    _sin_r2_ni_lanzar(monkeypatch)
    app["c"].post(f"/cliente/acme/referentes/{ids[0]}/recrear/generar",
                  data={"producto_id": "espejo_led", "formato": "1:1", "tipo": "imagen", "campos_vista": "1",
                        "modos_vista": "1"})
    app["c"].post(f"/cliente/acme/referentes/{ids[0]}/recrear/generar",
                  data={"producto_id": "espejo_led", "formato": "1:1", "tipo": "imagen", "campos_vista": "1",
                        "modos_vista": "1", "modo": "libre", "prompt": "  ", "prompt_editado": "1"})
    assert creative_flow.cargar("acme") == {}


def test_recrear_generar_video_una_sola_pieza_sin_texto(app, monkeypatch):
    import creative_flow
    ids = _sembrar()
    _con_lectura(ids[0])
    lanzados = _sin_r2_ni_lanzar(monkeypatch)
    app["c"].post(f"/cliente/acme/referentes/{ids[0]}/recrear/generar",
                  data={"producto_id": "espejo_led", "formato": "9:16", "tipo": "video", "campos_vista": "1",
                        "modo": ["fiel", "libre"]})
    assert len(lanzados) == 1
    entry = creative_flow.cargar("acme")[lanzados[0]]
    assert entry["tipo"] == "video" and "Ningún texto en la imagen." in entry["prompt_relleno"]
    assert "Cámara fija" in entry["prompt_relleno"] and " · " not in entry["accion_central"]


def test_recrear_adaptar_devuelve_textos_alineados(app, monkeypatch):
    import json
    from referentes import recrear
    ids = _sembrar()
    _con_lectura(ids[0])
    monkeypatch.setattr(recrear, "_llamar", lambda texto, max_tokens: (json.dumps(
        {"textos": ["40% OFF", "Marca X"], "prompt": "P", "angulo": {}}), 100, 30))
    r = app["c"].post(f"/cliente/acme/referentes/{ids[0]}/recrear/adaptar",
                      json={"producto_id": "espejo_led", "textos": ["50% OFF", ""], "traer_textos": True})
    assert r.status_code == 200 and r.get_json()["textos"] == ["40% OFF", ""]


def test_pestana_referentes_trae_el_js_de_recrear_fiel():
    """El JS del formulario vive en la pestaña (los <script> de un fragmento
    cargado por fetch nunca corren): que no se pierda nada de Recrear fiel."""
    import pathlib
    texto = pathlib.Path("templates/_tab_referentes.html").read_text(encoding="utf-8")
    for marca in ("data-recrear-leer", "data-recrear-modo", "data-recrear-editado", "data-recrear-texto",
                  "lecturasEnCurso", "formato_elegido", "modos_vista", "traer_textos", "ref:fragmento"):
        assert marca in texto, marca


# --- Recrear como video: igual (imagen fiel animada) y variación (spec §12) ---

def test_recrear_formulario_video_ofrece_igual_variacion_y_modelo(app):
    ids = _sembrar()
    _con_lectura(ids[0])
    html = app["c"].get(f"/cliente/acme/referentes/{ids[0]}/recrear?tipo=video").data.decode()
    assert 'name="modo" value="fiel"' in html and 'name="modo" value="libre"' in html
    assert 'name="modelo_animar"' in html and 'value="seedance25" selected' in html and 'value="wan3"' in html
    assert 'name="prompt_fiel"' in html and 'name="prompt_animar"' in html and "primer fotograma" in html
    assert "Generar 2 videos" in html and 'data-texto-fiel="' in html and 'data-texto-libre="' in html
    con_wan = app["c"].get(f"/cliente/acme/referentes/{ids[0]}/recrear?tipo=video&modelo_animar=wan3").data.decode()
    assert 'value="wan3" selected' in con_wan


def test_recrear_video_igual_crea_la_imagen_que_se_anima_y_la_variacion(app, monkeypatch):
    import creative_flow
    ids = _sembrar()
    _con_lectura(ids[0])
    lanzados = _sin_r2_ni_lanzar(monkeypatch)
    r = app["c"].post(f"/cliente/acme/referentes/{ids[0]}/recrear/generar",
                      data={"producto_id": "espejo_led", "formato": "9:16", "tipo": "video", "campos_vista": "1",
                            "traer_textos": "1", "texto_0": "40% OFF", "texto_1": "", "modos_vista": "1",
                            "modo": ["fiel", "libre"], "modelo_animar": "wan3"})
    assert r.status_code == 302 and len(lanzados) == 2
    sesiones = creative_flow.cargar("acme")
    imagen, variacion = sesiones[lanzados[0]], sesiones[lanzados[1]]
    assert imagen["tipo"] == "imagen" and imagen["modelo"] == "seedream_v5_pro" and imagen["recrear_modo"] == "fiel"
    assert "Edita Image 1" in imagen["prompt_relleno"] and "cambia «50% OFF» por «40% OFF»" in imagen["prompt_relleno"]
    animar = imagen["animar_despues"]
    assert animar["modelo"] == "wan3" and animar["duracion"] == 8 and animar["formato"] == "9:16"
    assert "primer fotograma" in animar["prompt"] and animar["titulo"] == "Recrear: 40% OFF · igual · video"
    assert imagen["accion_central"] == "Recrear: 40% OFF · igual"
    assert variacion["tipo"] == "video" and variacion["modelo"] == "wan3" and variacion["recrear_modo"] == "libre"
    assert variacion["accion_central"] == "Recrear: 40% OFF · variación" and "Cámara fija" in variacion["prompt_relleno"]


def test_recrear_video_modelo_desconocido_usa_seedance_y_respeta_el_prompt_editado(app, monkeypatch):
    import creative_flow
    ids = _sembrar()
    lanzados = _sin_r2_ni_lanzar(monkeypatch)
    app["c"].post(f"/cliente/acme/referentes/{ids[0]}/recrear/generar",
                  data={"producto_id": "espejo_led", "formato": "9:16", "tipo": "video", "campos_vista": "1",
                        "modos_vista": "1", "modo": "fiel", "modelo_animar": "otro",
                        "prompt_animar": "MI ANIMACION", "prompt_animar_editado": "1"})
    assert len(lanzados) == 1
    animar = creative_flow.cargar("acme")[lanzados[0]]["animar_despues"]
    assert animar["modelo"] == "seedance25" and animar["prompt"] == "MI ANIMACION"


def test_recrear_video_con_el_formulario_viejo_sigue_siendo_un_solo_video(app, monkeypatch):
    """Un formulario de video abierto antes del despliegue no manda
    `modos_vista`: hace un solo video, como antes, y nunca la animación
    (nadie paga una imagen + Seedance sin haberlo visto)."""
    import creative_flow
    ids = _sembrar()
    lanzados = _sin_r2_ni_lanzar(monkeypatch)
    app["c"].post(f"/cliente/acme/referentes/{ids[0]}/recrear/generar",
                  data={"producto_id": "espejo_led", "formato": "9:16", "tipo": "video", "campos_vista": "1"})
    assert len(lanzados) == 1
    entry = creative_flow.cargar("acme")[lanzados[0]]
    assert entry["tipo"] == "video" and "animar_despues" not in entry


def test_pestana_referentes_trae_el_js_de_recrear_como_video():
    import pathlib
    texto = pathlib.Path("templates/_tab_referentes.html").read_text(encoding="utf-8")
    for marca in ('modelo_animar', "'data-texto-' + clave"):
        assert marca in texto, marca


def test_detalle_de_crear_dice_que_la_imagen_se_anima(app, monkeypatch):
    import creative_flow
    import trabajos
    monkeypatch.setattr(trabajos, "en_curso", lambda job_id: False)
    cf = creative_flow.crear("acme", [], ["Espejo LED"], [], "Recrear: X · igual", 0, "", "A")
    creative_flow.actualizar("acme", cf, tipo="imagen", estado="video_generando",
                             animar_despues={"modelo": "wan3", "titulo": "Recrear: X · igual · video"})
    html = app["c"].get(f"/cliente/acme/creative_flow/{cf}/detalle").data.decode()
    assert "se anima sola en video" in html
    creative_flow.actualizar("acme", cf, estado="video_listo",
                             animar_despues={"modelo": "wan3", "titulo": "Recrear: X · igual · video", "cf_video": "cf_2"})
    assert "Recrear: X · igual · video" in app["c"].get(f"/cliente/acme/creative_flow/{cf}/detalle").data.decode()
    creative_flow.actualizar("acme", cf, animar_error="La imagen está lista, pero no se pudo lanzar su video (X).")
    assert "no se pudo lanzar su video" in app["c"].get(f"/cliente/acme/creative_flow/{cf}/detalle").data.decode()


def test_recrear_video_usa_el_formato_mas_parecido_que_admite_el_modelo(app, monkeypatch):
    """Wan 3.0 no tiene 4:5: va a 3:4 (el más parecido), no al 9:16 por defecto."""
    import creative_flow
    ids = _sembrar()
    lanzados = _sin_r2_ni_lanzar(monkeypatch)
    app["c"].post(f"/cliente/acme/referentes/{ids[0]}/recrear/generar",
                  data={"producto_id": "espejo_led", "formato": "4:5", "tipo": "video", "campos_vista": "1",
                        "modos_vista": "1", "modo": ["fiel", "libre"], "modelo_animar": "wan3"})
    imagen, variacion = (creative_flow.cargar("acme")[c] for c in lanzados)
    assert imagen["aspect_ratio"] == "4:5" and imagen["animar_despues"]["formato"] == "3:4"
    assert variacion["aspect_ratio"] == "3:4"
