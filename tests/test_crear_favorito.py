"""El corazón de las tarjetas de Crear (pedido del 2026-10-08): marcar las
versiones que se van a usar para separarlas de las que no."""


def _cliente_admin(dashboard):
    dashboard.app.config["TESTING"] = True
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "admin"
        s["rol"] = "admin"
        s["cliente"] = None
    return c


def _sesion_video_listo(cliente="acme"):
    import creative_flow as cf
    cf_id = cf.crear(cliente, [], ["Chancla Rose"], [], "la persona camina", 8, "", "A")
    cf.actualizar(cliente, cf_id, estado="video_listo", video_url="https://r2/clon.mp4", enfoque="producto")
    return cf_id


def test_marcar_y_desmarcar_conserva_el_resto_del_extra(base_temporal):
    import creative_flow as cf
    cf_id = _sesion_video_listo()
    assert cf.marcar_favorito("acme", cf_id, True)
    entry = cf.cargar("acme")[cf_id]
    assert entry["favorito"] is True and entry["accion_central"] == "la persona camina"
    assert entry["estado"] == "video_listo"
    assert cf.marcar_favorito("acme", cf_id, False)
    assert "favorito" not in cf.cargar("acme")[cf_id]


def test_otro_proyecto_no_puede_marcar(base_temporal):
    import creative_flow as cf
    cf_id = _sesion_video_listo("acme")
    assert cf.marcar_favorito("otro", cf_id, True) is False
    assert "favorito" not in cf.cargar("acme")[cf_id]


def test_la_copia_no_hereda_el_corazon(base_temporal):
    import creative_flow as cf
    cf_id = _sesion_video_listo()
    cf.marcar_favorito("acme", cf_id, True)
    hija = cf.duplicar("acme", cf_id)
    assert "favorito" not in cf.cargar("acme")[hija]


def test_ruta_por_fetch_y_tarjeta(base_temporal):
    import dashboard
    cf_id = _sesion_video_listo()
    c = _cliente_admin(dashboard)
    r = c.post(f"/cliente/acme/creative_flow/{cf_id}/favorito", data={"favorito": "1"},
               headers={"X-Requested-With": "fetch"})
    assert r.status_code == 200 and r.get_json() == {"ok": True, "favorito": True}
    html = c.get("/cliente/acme/crear/tarjetas").get_data(as_text=True)
    assert 'class="generado-fav activo"' in html and 'aria-pressed="true"' in html
    assert 'name="favorito" value="0"' in html
    r = c.post(f"/cliente/acme/creative_flow/{cf_id}/favorito", data={"favorito": "0"})
    assert r.status_code == 302 and r.headers["Location"].endswith("#creativeflowplus")
    html = c.get("/cliente/acme/crear/tarjetas").get_data(as_text=True)
    assert 'class="generado-fav"' in html and 'aria-pressed="false"' in html


def test_ruta_pieza_inexistente_y_otro_sitio(base_temporal):
    import dashboard
    cf_id = _sesion_video_listo()
    c = _cliente_admin(dashboard)
    r = c.post("/cliente/acme/creative_flow/cf_no_existe/favorito", data={"favorito": "1"},
               headers={"X-Requested-With": "fetch"})
    assert r.status_code == 404 and r.get_json()["ok"] is False
    r = c.post(f"/cliente/acme/creative_flow/{cf_id}/favorito", data={"favorito": "1"},
               headers={"Sec-Fetch-Site": "cross-site", "X-Requested-With": "fetch"})
    assert r.status_code == 403
    import creative_flow as cf
    assert "favorito" not in cf.cargar("acme")[cf_id]


def test_sin_corazon_mientras_se_genera(base_temporal):
    import creative_flow as cf
    import dashboard
    cf_id = cf.crear("acme", [], [], [], "algo", 8, "", "A")
    cf.actualizar("acme", cf_id, estado="video_generando")
    html = _cliente_admin(dashboard).get("/cliente/acme/crear/tarjetas").get_data(as_text=True)
    assert f'id="cf-{cf_id}"' in html and "generado-fav" not in html
